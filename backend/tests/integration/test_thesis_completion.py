"""Thesis -> examination -> completion -> graduation (BE-1.9, BE-1.10).

The closing marquee (arch §8.11): graduation records the award, closes funding, sets the student
to completed, and opens an `alumni` relationship on the SAME person.
"""
from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.modules.funding.constants import FundingStatus, FundingType
from app.modules.funding.models import FundingArrangement
from app.modules.identity.models import Permission, Role, User
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.models import Person, PersonRelationship
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Student

PERMS = [
    "student.read", "student.write", "person.read", "funding.read",
    # F4 — classification workflow uses progression.decide (exam board) and reports.signoff (Registry)
    "progression.decide", "reports.signoff",
]


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def ctx(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        perms = [Permission(code=c) for c in PERMS]
        s.add_all(perms); await s.flush()
        role = Role(name="PGR Administrator")
        s.add(role); await s.flush(); await s.refresh(role, ["permissions"]); role.permissions = perms
        user = User(email="u@t.com", password_hash=hash_password("pw"), is_active=True)
        # F4 — a second user so approver-separation on classification.confirm can be tested.
        user2 = User(email="u2@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add_all([user, user2]); await s.flush()
        await s.refresh(user, ["roles"]); user.roles = [role]
        await s.refresh(user2, ["roles"]); user2.roles = [role]

        person = Person(given_name="Sam", family_name="R")
        person.relationships = [PersonRelationship(
            relationship_type=PersonRelationshipType.student, valid_from=date(2021, 1, 1), valid_to=None,
        )]
        s.add(person); await s.flush()
        student = Student(person_id=person.id, student_ref="PGR-T", study_mode=StudyMode.full_time, status=StudentStatus.registered)
        s.add(student); await s.flush()
        s.add(FundingArrangement(
            student_id=student.id, funding_type=FundingType.research_council,
            stipend_amount=19000, currency="GBP", valid_from=date(2021, 1, 1), valid_to=None,
            status=FundingStatus.active,
        ))
        await s.commit()
        ids = {"student": str(student.id), "person": str(person.id)}

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/v1/auth/login", json={"email": "u@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        r2 = await client.post("/api/v1/auth/login", json={"email": "u2@t.com", "password": "pw"})
        h2 = {"Authorization": f"Bearer {r2.json()['accessToken']}"}
        ids["h2"] = h2  # F4 — second user for approver separation
        yield client, h, ids
    app.dependency_overrides.clear()


async def _to_approved_thesis(client, h, sid):
    t = (await client.post(f"/api/v1/students/{sid}/thesis/intention", headers=h, json={"title": "My Thesis"})).json()
    await client.post(f"/api/v1/theses/{t['id']}/submit", headers=h, json={"documentRef": "thesis.pdf"})
    await client.post(f"/api/v1/theses/{t['id']}/examination/outcome", headers=h, json={"outcome": "pass"})
    return t


@pytest.mark.asyncio
async def test_thesis_flow_reaches_approved(ctx):
    client, h, ids = ctx
    await _to_approved_thesis(client, h, ids["student"])
    t = (await client.get(f"/api/v1/students/{ids['student']}/thesis", headers=h)).json()
    assert t["status"] == "approved"
    assert t["examination"]["outcome"] == "pass"


@pytest.mark.asyncio
async def test_cannot_confirm_completion_before_thesis_approved(ctx):
    client, h, ids = ctx
    r = await client.post(f"/api/v1/students/{ids['student']}/completion/confirm", headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "workflow_error"


@pytest.mark.asyncio
async def test_cannot_graduate_before_confirm(ctx):
    client, h, ids = ctx
    await _to_approved_thesis(client, h, ids["student"])
    r = await client.post(f"/api/v1/students/{ids['student']}/graduation", headers=h)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_graduation_closes_the_loop(ctx):
    client, h, ids = ctx
    sid, pid = ids["student"], ids["person"]
    await _to_approved_thesis(client, h, sid)

    r = await client.post(f"/api/v1/students/{sid}/completion/confirm", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "award_confirmed"

    # F4 — classification must reach 'published' before graduation.
    h2 = ids["h2"]
    r = await client.post(f"/api/v1/students/{sid}/classification/propose", headers=h,
                          json={"classification": "PhD"})
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v1/students/{sid}/classification/confirm", headers=h2)
    assert r.status_code == 200 and r.json()["classificationState"] == "confirmed"
    r = await client.post(f"/api/v1/students/{sid}/classification/publish", headers=h)
    assert r.status_code == 200 and r.json()["classificationState"] == "published"

    r = await client.post(f"/api/v1/students/{sid}/graduation", headers=h)
    assert r.status_code == 200
    grad = r.json()
    assert grad["status"] == "graduated"
    assert grad["graduationDate"] is not None
    assert grad["award"]["title"] == "Doctor of Philosophy"

    # Student -> completed
    assert (await client.get(f"/api/v1/students/{sid}", headers=h)).json()["status"] == "completed"
    # Funding -> ended
    funding = (await client.get(f"/api/v1/students/{sid}/funding", headers=h)).json()
    assert all(a["status"] == "ended" for a in funding)
    # Person -> student closed, alumni current (same person)
    rels = {x["relationshipType"]: x["validTo"] for x in (await client.get(f"/api/v1/persons/{pid}/relationships", headers=h)).json()}
    assert rels["student"] is not None
    assert rels["alumni"] is None
