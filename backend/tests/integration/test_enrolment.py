"""ICR G2 — the direct enrolment door.

ICR runs recruitment in a separate system: the first time this platform sees a student, they are
already accepted and pre-enrolment. So there must be a way to create a student WITHOUT an
opportunity/offer chain. What must hold:
- enrol a brand-new person in one call -> Person + Student (registered by default)
- enrol an existing person by id -> attaches, no duplicate Person
- an accepted-but-not-yet-registered student can be recorded as `prospective`
- an optional funding arrangement is created in the same call
- the identity thread is preserved: a `student` relationship is opened
- you cannot enrol the same person twice (already a student -> 409)
- exactly one of personId / person must be supplied (else 422)
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.funding.models import FundingArrangement
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.models import Person, PersonRelationship
from app.modules.student_record.models import Programme, Student


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    ids = {}
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        user = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]

        prog = Programme(name="PhD", code="PHD"); s.add(prog); await s.flush()
        ids["programme"] = str(prog.id)

        # An existing person with no student record yet — the "attach existing" case.
        existing = Person(given_name="Ada", family_name="Okonkwo", email="ada@t.com")
        s.add(existing); await s.flush()
        ids["existing_person"] = str(existing.id)
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h, ids, sm
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_enrol_a_new_person_creates_person_and_student(ctx):
    c, h, ids, sm = ctx
    r = await c.post("/api/v1/students/enrol", headers=h, json={
        "person": {"givenName": "Bruno", "familyName": "Costa", "email": "bruno@t.com"},
        "programmeId": ids["programme"],
        "startDate": "2026-09-01",
        "studyMode": "full_time",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "registered"
    assert body["studentRef"].startswith("PGR-")

    async with sm() as s:
        person = (await s.execute(
            select(Person).where(Person.email == "bruno@t.com")
        )).scalar_one()
        # Student exists and reuses the new person id.
        student = (await s.execute(
            select(Student).where(Student.person_id == person.id)
        )).scalar_one()
        assert str(student.programme_id) == ids["programme"]
        # A student relationship was opened and is current.
        rels = (await s.execute(
            select(PersonRelationship).where(PersonRelationship.person_id == person.id)
        )).scalars().all()
        assert any(
            rel.relationship_type == PersonRelationshipType.student and rel.valid_to is None
            for rel in rels
        )


@pytest.mark.asyncio
async def test_enrol_existing_person_by_id_does_not_duplicate(ctx):
    c, h, ids, sm = ctx
    r = await c.post("/api/v1/students/enrol", headers=h, json={
        "personId": ids["existing_person"],
        "programmeId": ids["programme"],
        "status": "prospective",
    })
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "prospective"

    async with sm() as s:
        people = (await s.execute(
            select(Person).where(Person.email == "ada@t.com")
        )).scalars().all()
        assert len(people) == 1  # attached, not duplicated
        student = (await s.execute(
            select(Student).where(Student.person_id == people[0].id)
        )).scalar_one()
        assert str(student.id)


@pytest.mark.asyncio
async def test_enrol_with_funding_creates_arrangement(ctx):
    c, h, ids, sm = ctx
    r = await c.post("/api/v1/students/enrol", headers=h, json={
        "person": {"givenName": "Chen", "familyName": "Li", "email": "chen@t.com"},
        "programmeId": ids["programme"],
        "funding": {"fundingType": "self_funded", "validFrom": "2026-09-01"},
    })
    assert r.status_code == 201, r.text
    student_id = uuid.UUID(r.json()["id"])
    async with sm() as s:
        arrangements = (await s.execute(
            select(FundingArrangement).where(FundingArrangement.student_id == student_id)
        )).scalars().all()
        assert len(arrangements) == 1


@pytest.mark.asyncio
async def test_cannot_enrol_the_same_person_twice(ctx):
    c, h, ids, _ = ctx
    payload = {"personId": ids["existing_person"], "programmeId": ids["programme"]}
    first = await c.post("/api/v1/students/enrol", headers=h, json=payload)
    assert first.status_code == 201, first.text
    second = await c.post("/api/v1/students/enrol", headers=h, json=payload)
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_must_supply_exactly_one_person_source(ctx):
    c, h, ids, _ = ctx
    # Neither.
    r1 = await c.post("/api/v1/students/enrol", headers=h, json={"programmeId": ids["programme"]})
    assert r1.status_code == 422, r1.text
    # Both.
    r2 = await c.post("/api/v1/students/enrol", headers=h, json={
        "personId": ids["existing_person"],
        "person": {"givenName": "X", "familyName": "Y"},
        "programmeId": ids["programme"],
    })
    assert r2.status_code == 422, r2.text
