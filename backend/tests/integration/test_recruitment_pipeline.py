"""Recruitment -> Admissions -> Student pipeline (BE-1.2..1.5).

The marquee assertion: accepting an offer creates a student that REUSES the applicant's
person_id (arch §8.6), converts the application, and opens a student identity on the person.
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
from app.modules.identity.models import Permission, Role, User
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.models import Person, PersonRelationship
from app.modules.student_record.models import Department, Programme

PERMS = [
    "person.read", "person.write", "recruitment.read", "recruitment.write",
    "student.read", "student.write",
]


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def ctx(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        perms = [Permission(code=c) for c in PERMS]
        s.add_all(perms)
        await s.flush()
        role = Role(name="Admin")
        s.add(role)
        await s.flush()
        await s.refresh(role, ["permissions"])
        role.permissions = perms
        user = User(email="a@example.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user)
        await s.flush()
        await s.refresh(user, ["roles"])
        user.roles = [role]

        dept = Department(name="CS", code="CS")
        s.add(dept)
        await s.flush()
        s.add(Programme(name="PhD CS", code="PHD-CS", department_id=dept.id))

        person = Person(given_name="Sam", family_name="Rivers", email="sam@example.com")
        person.relationships = [
            PersonRelationship(
                relationship_type=PersonRelationshipType.applicant,
                valid_from=date(2025, 1, 1), valid_to=None,
            )
        ]
        s.add(person)
        await s.commit()
        person_id = str(person.id)

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "pw"})
        token = r.json()["accessToken"]
        yield client, {"Authorization": f"Bearer {token}"}, person_id
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_applicant_converts_to_student_same_person_id(ctx):
    client, h, person_id = ctx

    # 1) Opportunity
    r = await client.post("/api/v1/opportunities", headers=h, json={"title": "PhD in ML"})
    assert r.status_code == 201, r.text
    opp_id = r.json()["id"]

    # 2) Application (opportunity-led)
    r = await client.post(
        "/api/v1/applications", headers=h,
        json={"personId": person_id, "route": "opportunity_led", "researchOpportunityId": opp_id},
    )
    assert r.status_code == 201, r.text
    app_id = r.json()["id"]
    assert r.json()["currentStage"] == "applicant"

    # 3) Offer -> issue -> accept
    r = await client.post(f"/api/v1/applications/{app_id}/offer", headers=h, json={})
    assert r.status_code == 201, r.text
    offer_id = r.json()["id"]

    r = await client.post(f"/api/v1/offers/{offer_id}/issue", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "issued"

    r = await client.post(f"/api/v1/offers/{offer_id}/accept", headers=h, json={})
    assert r.status_code == 201, r.text
    student = r.json()

    # THE MARQUEE: student reuses the applicant's person_id.
    assert student["personId"] == person_id
    assert student["studentRef"].startswith("PGR-")

    # Application is now converted.
    r = await client.get(f"/api/v1/applications/{app_id}", headers=h)
    assert r.json()["currentStage"] == "converted"

    # Person now holds a current student identity; applicant is closed.
    r = await client.get(f"/api/v1/persons/{person_id}/relationships", headers=h)
    rels = {x["relationshipType"]: x["validTo"] for x in r.json()}
    assert rels["student"] is None          # current
    assert rels["applicant"] is not None    # closed


@pytest.mark.asyncio
async def test_cannot_accept_unissued_offer(ctx):
    client, h, person_id = ctx
    # A student-led application must carry its research intent (route integrity, Phase 6.0).
    r = await client.post("/api/v1/applications", headers=h,
                          json={"personId": person_id, "route": "student_led",
                                "proposalDocumentRef": "proposal.pdf"})
    app_id = r.json()["id"]
    r = await client.post(f"/api/v1/applications/{app_id}/offer", headers=h, json={})
    offer_id = r.json()["id"]
    # Accept without issuing -> workflow_error (422)
    r = await client.post(f"/api/v1/offers/{offer_id}/accept", headers=h, json={})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "workflow_error"


@pytest.mark.asyncio
async def test_opportunity_invalid_transition(ctx):
    client, h, _ = ctx
    r = await client.post("/api/v1/opportunities", headers=h, json={"title": "X"})
    oid = r.json()["id"]
    # draft -> filled is not allowed
    r = await client.post(f"/api/v1/opportunities/{oid}/transition", headers=h, json={"toStatus": "filled"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "workflow_error"
