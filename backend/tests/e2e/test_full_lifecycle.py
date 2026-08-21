"""End-to-end: the whole PGR lifecycle in one journey (BE-1.12, closes Phase 1 MVP).

person -> opportunity -> application -> advance -> offer -> issue -> accept (student, SAME
person_id) -> supervisor -> milestone submit/decide (next generated) -> funding -> thesis
intention/submit/examination -> completion confirm -> graduation -> alumni.

Asserts the identity thread is preserved end to end and the closing state is correct.
"""
from __future__ import annotations

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
from app.modules.progression.models import MilestoneDefinition
from app.modules.student_record.models import Department, Programme

ALL_PERMS = [
    "person.read", "person.write", "student.read", "student.write",
    "recruitment.read", "recruitment.write", "funding.read", "funding.change",
    "progression.read", "progression.decide", "reporting.read", "admin.configure",
]


@pytest_asyncio.fixture
async def client():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = [Permission(code=c) for c in ALL_PERMS]
        s.add_all(perms); await s.flush()
        role = Role(name="Institution Administrator")   # unrestricted scope + all permissions
        s.add(role); await s.flush(); await s.refresh(role, ["permissions"]); role.permissions = perms
        user = User(email="admin@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]
        dept = Department(name="CS", code="CS"); s.add(dept); await s.flush()
        prog = Programme(name="PhD CS", code="PHD-CS", department_id=dept.id); s.add(prog); await s.flush()
        s.add(MilestoneDefinition(programme_id=prog.id, name="Induction", due_offset_days=0))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "admin@t.com", "password": "pw"})
        c.headers.update({"Authorization": f"Bearer {r.json()['accessToken']}"})
        yield c
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_full_lifecycle_applicant_to_alumni(client):
    c = client

    async def post(path, json=None):
        r = await c.post(path, json=json or {})
        assert r.status_code in (200, 201), f"{path} -> {r.status_code}: {r.text}"
        return r.json()

    # 1) Person (applicant) + opportunity + application
    person = await post("/api/v1/persons", {"givenName": "Jordan", "familyName": "Lee", "email": "jordan.lee@example.com"})
    pid = person["id"]
    opp = await post("/api/v1/opportunities", {"title": "PhD in Robotics"})
    appn = await post("/api/v1/applications", {"personId": pid, "route": "opportunity_led", "researchOpportunityId": opp["id"]})
    aid = appn["id"]

    # 2) Advance -> selected, then offer -> issue -> accept
    await post(f"/api/v1/applications/{aid}/advance", {"toStage": "selected", "reason": "strong"})
    offer = await post(f"/api/v1/applications/{aid}/offer", {})
    await post(f"/api/v1/offers/{offer['id']}/issue")
    student = await post(f"/api/v1/offers/{offer['id']}/accept", {})
    sid = student["id"]
    assert student["personId"] == pid, "student must reuse the applicant's person_id"

    # 3) Supervisor
    await post(f"/api/v1/students/{sid}/supervisors", {"supervisorPersonId": pid, "role": "primary"})

    # 4) Progression: milestone generated -> submit -> decide progress
    milestones = (await c.get(f"/api/v1/students/{sid}/milestones")).json()
    assert len(milestones) == 1
    mid = milestones[0]["id"]
    await post(f"/api/v1/milestones/{mid}/submit", {"studentSubmissionRef": "m1.pdf"})
    decided = await post(f"/api/v1/milestones/{mid}/decide", {"outcome": "progress"})
    assert decided["status"] == "decided"

    # 5) Funding
    await post(f"/api/v1/students/{sid}/funding", {"fundingType": "research_council", "stipendAmount": "19000", "currency": "GBP"})

    # 6) Thesis: intention -> submit -> examination pass
    thesis = await post(f"/api/v1/students/{sid}/thesis/intention", {"title": "Robotics Thesis"})
    tid = thesis["id"]
    await post(f"/api/v1/theses/{tid}/submit", {"documentRef": "thesis.pdf"})
    approved = await post(f"/api/v1/theses/{tid}/examination/outcome", {"outcome": "pass"})
    assert approved["status"] == "approved"

    # 7) Completion -> graduation
    await post(f"/api/v1/students/{sid}/completion/confirm")
    grad = await post(f"/api/v1/students/{sid}/graduation")
    assert grad["status"] == "graduated"
    assert grad["award"]["title"] == "Doctor of Philosophy"

    # --- Closing assertions: the loop is closed on the SAME person ---
    assert (await c.get(f"/api/v1/students/{sid}")).json()["status"] == "completed"
    funding = (await c.get(f"/api/v1/students/{sid}/funding")).json()
    assert all(f["status"] == "ended" for f in funding)
    rels = {x["relationshipType"]: x["validTo"] for x in (await c.get(f"/api/v1/persons/{pid}/relationships")).json()}
    assert rels["student"] is not None      # student identity closed
    assert rels["alumni"] is None           # alumni is current

    # Timeline spans the journey on one person.
    timeline = (await c.get(f"/api/v1/persons/{pid}/timeline")).json()
    labels = " ".join(e["label"] for e in timeline["entries"])
    assert "Student" in labels and "Alumni" in labels
