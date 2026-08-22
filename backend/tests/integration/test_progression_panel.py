"""Phase 4B.6 — progression panels, conditions, outcome letters, and appeals.

A formal review needs a properly constituted panel (chair + independent assessor); conditional
outcomes must carry written conditions and schedule a re-review; students may appeal within the
appeal window, and an upheld appeal reopens the milestone.
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
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.progression.models import MilestoneDefinition
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student
from app.modules.supervision.constants import SupervisionStatus, SupervisorRole
from app.modules.supervision.models import SupervisorRelationship

PERMS = ["student.read", "person.read", "progression.read", "progression.decide", "admin.configure"]


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    ids = {}
    async with sm() as s:
        perms = [Permission(code=c) for c in PERMS]
        s.add_all(perms); await s.flush()
        role = Role(name="PGR Administrator")
        s.add(role); await s.flush(); await s.refresh(role, ["permissions"]); role.permissions = perms
        user = User(email="u@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]

        prog = Programme(name="PhD", code="PHD"); s.add(prog); await s.flush()
        # A formal review: the programme configuration says a panel is required.
        confirm = MilestoneDefinition(
            programme_id=prog.id, name="Confirmation", due_offset_days=270,
            review_panel={"required": True},
        )
        s.add(confirm); await s.flush()
        ids["definition"] = str(confirm.id)

        student_person = Person(given_name="Sam", family_name="Rao")
        chair = Person(given_name="Cho", family_name="Chair")
        assessor = Person(given_name="Ind", family_name="Assessor")
        supervisor = Person(given_name="Sue", family_name="Super")
        s.add_all([student_person, chair, assessor, supervisor]); await s.flush()
        ids |= {"chair": str(chair.id), "assessor": str(assessor.id), "supervisor": str(supervisor.id)}

        student = Student(
            person_id=student_person.id, student_ref="PGR-P", programme_id=prog.id,
            start_date=date(2024, 1, 1), study_mode=StudyMode.full_time, status=StudentStatus.registered,
        )
        s.add(student); await s.flush()
        ids["student"] = str(student.id)
        s.add(SupervisorRelationship(
            student_id=student.id, supervisor_person_id=supervisor.id, role=SupervisorRole.primary,
            status=SupervisionStatus.active, valid_from=date(2024, 1, 1),
        ))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/v1/auth/login", json={"email": "u@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield client, h, ids
    app.dependency_overrides.clear()
    await eng.dispose()


async def _milestone(client, h, sid):
    rows = (await client.get(f"/api/v1/students/{sid}/milestones", headers=h)).json()
    return rows[0]["id"]


@pytest.mark.asyncio
async def test_formal_review_requires_complete_panel(ctx):
    client, h, ids = ctx
    mid = await _milestone(client, h, ids["student"])
    # No panel -> decision refused (this definition requires one).
    r = await client.post(f"/api/v1/milestones/{mid}/decide", headers=h,
                          json={"outcome": "progress", "rationale": "looks fine"})
    assert r.status_code == 422 and "Panel is incomplete" in r.json()["error"]["message"]

    # Chair alone is still incomplete.
    await client.post(f"/api/v1/milestones/{mid}/panel", headers=h,
                      json={"personId": ids["chair"], "role": "chair"})
    r = await client.post(f"/api/v1/milestones/{mid}/decide", headers=h, json={"outcome": "progress"})
    assert r.status_code == 422

    # Add the independent assessor -> decision allowed.
    panel = await client.post(f"/api/v1/milestones/{mid}/panel", headers=h,
                              json={"personId": ids["assessor"], "role": "independent_assessor"})
    assert panel.status_code == 201
    members = panel.json()
    assert len(members) == 2
    assert any(m["role"] == "independent_assessor" and m["isIndependent"] for m in members)

    ok = await client.post(f"/api/v1/milestones/{mid}/decide", headers=h,
                           json={"outcome": "progress", "rationale": "Good progress"})
    assert ok.status_code == 200 and ok.json()["status"] == "decided"


@pytest.mark.asyncio
async def test_supervisor_cannot_be_independent_assessor(ctx):
    client, h, ids = ctx
    mid = await _milestone(client, h, ids["student"])
    r = await client.post(f"/api/v1/milestones/{mid}/panel", headers=h,
                          json={"personId": ids["supervisor"], "role": "independent_assessor"})
    assert r.status_code == 422
    assert "independent assessor" in r.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_conditional_outcome_requires_conditions_and_schedules_re_review(ctx):
    client, h, ids = ctx
    mid = await _milestone(client, h, ids["student"])
    await client.post(f"/api/v1/milestones/{mid}/panel", headers=h, json={"personId": ids["chair"], "role": "chair"})
    await client.post(f"/api/v1/milestones/{mid}/panel", headers=h,
                      json={"personId": ids["assessor"], "role": "independent_assessor"})

    # progress_with_conditions with no conditions -> refused.
    bad = await client.post(f"/api/v1/milestones/{mid}/decide", headers=h,
                            json={"outcome": "progress_with_conditions"})
    assert bad.status_code == 422 and "conditions" in bad.json()["error"]["message"].lower()

    good = await client.post(f"/api/v1/milestones/{mid}/decide", headers=h, json={
        "outcome": "progress_with_conditions",
        "conditions": "Submit a revised literature review.",
        "outcomeLetter": "Dear Sam, the panel has agreed you may continue subject to conditions.",
    })
    assert good.status_code == 200

    detail = (await client.get(f"/api/v1/milestones/{mid}/review", headers=h)).json()
    assert detail["conditions"].startswith("Submit a revised")
    assert detail["reReviewDue"] is not None      # re-review scheduled
    assert detail["appealDeadline"] is not None   # appeal window opened
    assert detail["conditionsMet"] is False
    assert detail["outcomeLetter"].startswith("Dear Sam")

    signed = await client.post(f"/api/v1/milestones/{mid}/conditions/sign-off", headers=h)
    assert signed.status_code == 200 and signed.json()["conditionsMet"] is True


@pytest.mark.asyncio
async def test_appeal_flow_upheld_reopens_milestone(ctx):
    client, h, ids = ctx
    mid = await _milestone(client, h, ids["student"])
    await client.post(f"/api/v1/milestones/{mid}/panel", headers=h, json={"personId": ids["chair"], "role": "chair"})
    await client.post(f"/api/v1/milestones/{mid}/panel", headers=h,
                      json={"personId": ids["assessor"], "role": "independent_assessor"})
    await client.post(f"/api/v1/milestones/{mid}/decide", headers=h,
                      json={"outcome": "further_review", "conditions": "Resubmit chapter 3."})

    # Appeal requires grounds.
    assert (await client.post(f"/api/v1/milestones/{mid}/appeals", headers=h, json={"grounds": "  "})).status_code == 422

    a = await client.post(f"/api/v1/milestones/{mid}/appeals", headers=h,
                          json={"grounds": "Procedural irregularity: the panel did not read my submission."})
    assert a.status_code == 201 and a.json()["status"] == "submitted"
    appeal_id = a.json()["id"]

    # No duplicate open appeals.
    dup = await client.post(f"/api/v1/milestones/{mid}/appeals", headers=h, json={"grounds": "again"})
    assert dup.status_code == 409

    listed = (await client.get(f"/api/v1/milestones/{mid}/appeals", headers=h)).json()
    assert len(listed) == 1

    # Uphold it -> milestone reopens for a fresh review.
    decided = await client.post(f"/api/v1/milestones/appeals/{appeal_id}/decide", headers=h,
                                json={"status": "upheld", "decisionNote": "Panel to reconvene."})
    assert decided.status_code == 200 and decided.json()["status"] == "upheld"
    rows = (await client.get(f"/api/v1/students/{ids['student']}/milestones", headers=h)).json()
    reopened = next(r for r in rows if r["id"] == mid)
    assert reopened["status"] == "under_review"
