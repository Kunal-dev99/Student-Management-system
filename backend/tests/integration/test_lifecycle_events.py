"""Phase 6.5 — PGR exception lifecycle (CIO vision GAP-06).

Suspensions, extensions and mode changes change research timelines. What must hold:
- requesting changes **nothing** — only approval moves dates (user decision: approval required)
- the **original** agreed end date is preserved and every adjustment is explainable
- only **undecided** milestones shift; a decided milestone is a historical fact
- overlapping suspensions are refused
- a suspended student is **not chased** for funding expiry or overdue tasks
- returning early or late corrects the provisional figure
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.funding.constants import FundingStatus, FundingType
from app.modules.funding.models import FundingArrangement
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone, MilestoneDefinition
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student

START = date(2026, 1, 1)
ORIGINAL_END = date(2029, 1, 1)


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    ids = {}
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        pgr_admin = Role(name="PGR Administrator"); s.add(pgr_admin); await s.flush()
        await s.refresh(pgr_admin, ["permissions"]); pgr_admin.permissions = list(perms.values())
        user = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"])
        # Both roles, mirroring the seeded admin — the approval task targets PGR Administrator.
        user.roles = [role, pgr_admin]

        # A requester who may ask but MUST NOT approve.
        req_role = Role(name="PGR Officer"); s.add(req_role); await s.flush()
        await s.refresh(req_role, ["permissions"])
        req_role.permissions = [perms["student.read"], perms["student.write"]]
        requester = User(email="req@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(requester); await s.flush(); await s.refresh(requester, ["roles"])
        requester.roles = [req_role]

        prog = Programme(name="PhD", code="PHD"); s.add(prog); await s.flush()
        defn = MilestoneDefinition(programme_id=prog.id, name="Confirmation", due_offset_days=270)
        s.add(defn); await s.flush()

        person = Person(given_name="Sam", family_name="Rao"); s.add(person); await s.flush()
        student = Student(
            person_id=person.id, student_ref="PGR-SUS", programme_id=prog.id,
            start_date=START, expected_end_date=ORIGINAL_END,
            study_mode=StudyMode.full_time, status=StudentStatus.active,
        )
        s.add(student); await s.flush()
        ids["student"] = str(student.id)

        # One undecided and one decided milestone — only the first should ever move.
        undecided = Milestone(student_id=student.id, milestone_definition_id=defn.id,
                              due_date=date(2026, 9, 28), status=MilestoneStatus.due)
        decided = Milestone(student_id=student.id, milestone_definition_id=defn.id,
                            due_date=date(2026, 2, 1), status=MilestoneStatus.decided)
        s.add_all([undecided, decided]); await s.flush()
        ids["undecided"] = str(undecided.id)
        ids["decided"] = str(decided.id)

        # Funding that expires soon — used to prove a suspended student is not chased.
        s.add(FundingArrangement(
            student_id=student.id, funding_type=FundingType.research_council,
            valid_from=START, valid_to=date.today() + timedelta(days=30),
            status=FundingStatus.active,
        ))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        async def token(email):
            r = await c.post("/api/v1/auth/login", json={"email": email, "password": "pw"})
            return {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, token, ids, sm
    app.dependency_overrides.clear()
    await eng.dispose()


async def _request_suspension(c, h, sid, start="2026-06-01", end="2026-09-01"):
    return await c.post(f"/api/v1/students/{sid}/lifecycle-events", headers=h, json={
        "eventType": "suspension", "reason": "Medical leave",
        "startDate": start, "endDate": end,
    })


# --------------------------------------------------------------------------------------
# Approval gate
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_alone_changes_nothing(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    r = await _request_suspension(c, h, ids["student"])
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "requested"
    assert r.json()["daysApplied"] is None

    student = (await c.get(f"/api/v1/students/{ids['student']}", headers=h)).json()
    assert student["status"] == "active"                       # not suspended yet
    assert student["expectedEndDate"] == ORIGINAL_END.isoformat()   # dates untouched


@pytest.mark.asyncio
async def test_requesting_raises_an_approval_task(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    await _request_suspension(c, h, ids["student"])
    tasks = (await c.get("/api/v1/tasks", headers=h)).json()
    assert any("approve suspension" in t["title"].lower() for t in tasks)


@pytest.mark.asyncio
async def test_requester_without_approve_permission_cannot_approve(ctx):
    c, token, ids, _ = ctx
    h_admin = await token("a@t.com")
    h_req = await token("req@t.com")
    ev = (await _request_suspension(c, h_req, ids["student"])).json()
    denied = await c.post(f"/api/v1/lifecycle-events/{ev['id']}/approve", headers=h_req, json={})
    assert denied.status_code == 403
    # The approver can.
    assert (await c.post(f"/api/v1/lifecycle-events/{ev['id']}/approve",
                         headers=h_admin, json={})).status_code == 200


# --------------------------------------------------------------------------------------
# Recalculation
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approved_suspension_extends_end_date_and_shifts_undecided_milestones(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    ev = (await _request_suspension(c, h, ids["student"], "2026-06-01", "2026-09-01")).json()
    result = (await c.post(f"/api/v1/lifecycle-events/{ev['id']}/approve", headers=h, json={})).json()

    days = (date(2026, 9, 1) - date(2026, 6, 1)).days          # 92
    recalc = result["recalculation"]
    assert result["event"]["daysApplied"] == days
    assert recalc["originalExpectedEnd"] == ORIGINAL_END.isoformat()
    assert recalc["newExpectedEnd"] == (ORIGINAL_END + timedelta(days=days)).isoformat()
    assert recalc["totalDaysApplied"] == days
    assert recalc["milestonesShifted"] == 1                    # only the undecided one

    student = (await c.get(f"/api/v1/students/{ids['student']}", headers=h)).json()
    assert student["status"] == "suspended"
    assert student["originalExpectedEndDate"] == ORIGINAL_END.isoformat()   # baseline preserved

    milestones = (await c.get(f"/api/v1/students/{ids['student']}/milestones", headers=h)).json()
    by_id = {m["id"]: m for m in milestones}
    assert by_id[ids["undecided"]]["dueDate"] == (date(2026, 9, 28) + timedelta(days=days)).isoformat()
    assert by_id[ids["decided"]]["dueDate"] == "2026-02-01"    # decided = historical fact, untouched


@pytest.mark.asyncio
async def test_extension_adds_days_and_stacks_with_suspension(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    ev = (await _request_suspension(c, h, ids["student"], "2026-06-01", "2026-09-01")).json()
    await c.post(f"/api/v1/lifecycle-events/{ev['id']}/approve", headers=h, json={})

    ext = (await c.post(f"/api/v1/students/{ids['student']}/lifecycle-events", headers=h, json={
        "eventType": "extension", "reason": "Fieldwork delayed by access issues",
        "startDate": "2027-01-01", "extensionDays": 60,
    })).json()
    result = (await c.post(f"/api/v1/lifecycle-events/{ext['id']}/approve", headers=h, json={})).json()

    recalc = result["recalculation"]
    assert recalc["totalDaysApplied"] == 92 + 60
    assert recalc["newExpectedEnd"] == (ORIGINAL_END + timedelta(days=152)).isoformat()
    assert len(recalc["breakdown"]) == 2                       # the arithmetic is itemised


@pytest.mark.asyncio
async def test_rejected_request_leaves_dates_untouched(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    ev = (await _request_suspension(c, h, ids["student"])).json()
    r = await c.post(f"/api/v1/lifecycle-events/{ev['id']}/reject", headers=h,
                     json={"note": "Insufficient evidence"})
    assert r.status_code == 200 and r.json()["event"]["status"] == "rejected"

    student = (await c.get(f"/api/v1/students/{ids['student']}", headers=h)).json()
    assert student["status"] == "active"
    assert student["expectedEndDate"] == ORIGINAL_END.isoformat()


# --------------------------------------------------------------------------------------
# Return
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_early_return_corrects_the_provisional_days(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    ev = (await _request_suspension(c, h, ids["student"], "2026-06-01", "2026-09-01")).json()
    await c.post(f"/api/v1/lifecycle-events/{ev['id']}/approve", headers=h, json={})

    # Returned a month early.
    result = (await c.post(f"/api/v1/students/{ids['student']}/return", headers=h,
                           json={"returnedOn": "2026-08-01"})).json()
    actual_days = (date(2026, 8, 1) - date(2026, 6, 1)).days   # 61, not 92
    assert result["event"]["daysApplied"] == actual_days
    assert result["recalculation"]["newExpectedEnd"] == (ORIGINAL_END + timedelta(days=actual_days)).isoformat()

    student = (await c.get(f"/api/v1/students/{ids['student']}", headers=h)).json()
    assert student["status"] == "active"


@pytest.mark.asyncio
async def test_cannot_return_a_student_who_is_not_suspended(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    r = await c.post(f"/api/v1/students/{ids['student']}/return", headers=h, json={})
    assert r.status_code == 422


# --------------------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_overlapping_suspensions_are_refused(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    await _request_suspension(c, h, ids["student"], "2026-06-01", "2026-09-01")
    clash = await _request_suspension(c, h, ids["student"], "2026-08-01", "2026-10-01")
    assert clash.status_code == 409
    assert "overlaps" in clash.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_suspension_requires_reason_and_sensible_dates(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    no_reason = await c.post(f"/api/v1/students/{ids['student']}/lifecycle-events", headers=h, json={
        "eventType": "suspension", "reason": "  ", "startDate": "2026-06-01", "endDate": "2026-09-01"})
    assert no_reason.status_code == 422
    backwards = await _request_suspension(c, h, ids["student"], "2026-09-01", "2026-06-01")
    assert backwards.status_code == 422


@pytest.mark.asyncio
async def test_double_approval_is_refused(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    ev = (await _request_suspension(c, h, ids["student"])).json()
    assert (await c.post(f"/api/v1/lifecycle-events/{ev['id']}/approve", headers=h, json={})).status_code == 200
    again = await c.post(f"/api/v1/lifecycle-events/{ev['id']}/approve", headers=h, json={})
    assert again.status_code == 409


# --------------------------------------------------------------------------------------
# A paused student is not chased (BE-6.5.4)
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_suspended_student_is_not_chased_for_expiring_funding(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    # Baseline: the scheduler flags this student's expiring funding.
    first = (await c.post("/api/v1/admin/scheduled-jobs/run", headers=h)).json()
    assert first["fundingExpiringFlagged"] == 1

    ev = (await _request_suspension(c, h, ids["student"])).json()
    await c.post(f"/api/v1/lifecycle-events/{ev['id']}/approve", headers=h, json={})

    # Now suspended: no new flag is raised (the earlier task still exists, but nothing new).
    second = (await c.post("/api/v1/admin/scheduled-jobs/run", headers=h)).json()
    assert second["fundingExpiringFlagged"] == 0


@pytest.mark.asyncio
async def test_worker_returns_students_whose_suspension_has_ended(ctx):
    """A suspension that has run its course should end itself on the next worker tick."""
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    start = (date.today() - timedelta(days=60)).isoformat()
    end = (date.today() - timedelta(days=5)).isoformat()       # already in the past
    ev = (await _request_suspension(c, h, ids["student"], start, end)).json()
    await c.post(f"/api/v1/lifecycle-events/{ev['id']}/approve", headers=h, json={})
    assert (await c.get(f"/api/v1/students/{ids['student']}", headers=h)).json()["status"] == "suspended"

    result = (await c.post("/api/v1/admin/scheduled-jobs/run", headers=h)).json()
    assert result["studentsReturnedFromSuspension"] == 1
    assert (await c.get(f"/api/v1/students/{ids['student']}", headers=h)).json()["status"] == "active"
