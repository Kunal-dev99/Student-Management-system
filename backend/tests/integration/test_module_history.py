"""Effective dating, Phase 3 — module enrolment dates and dated module status.

What must hold:
- a module enrolment gets the student's own dates: from the later of their start and 1 Aug, to
  31 Jul of the academic year (HESA ModuleInstance start / end)
- module status changes are dated history: a future-dated change waits for its day
- withdrawing (or interrupting) ends the module on that date
- dates set explicitly must fall within the student's time on a programme offering the module;
  a change needs a reason, and moving the start moves the status history's start too
- approving a suspension proposes the student's open modules; interrupting them is confirmed
  separately and ends each on the suspension date
- the backfill dates older enrolments and gives them a status history
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
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.student_record import fact_history
from app.modules.student_record.constants import ProgrammeType
from app.modules.student_record.models import Programme
from app.modules.taught.constants import ModuleEnrolmentStatus
from app.modules.taught.module_backfill import backfill_module_enrolments, check_module_enrolments
from app.modules.taught.module_history import ModuleStatusHistoryService
from app.modules.taught.models import ModuleEnrolment, ModuleEnrolmentStatusHistory

START = "2026-09-21"


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
        pgr = Role(name="PGR Administrator"); s.add(pgr); await s.flush()
        await s.refresh(pgr, ["permissions"]); pgr.permissions = list(perms.values())
        u = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role, pgr]
        msc = Programme(name="MSc Oncology", code="MSC-ONC", programme_type=ProgrammeType.taught,
                        taught_total_credits=180)
        other = Programme(name="MSc Neurology", code="MSC-NEU", programme_type=ProgrammeType.taught,
                          taught_total_credits=180)
        s.add_all([msc, other]); await s.flush()
        ids["msc"], ids["other"] = str(msc.id), str(other.id)
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        # A core module on the student's programme, created before they enrol so it auto-enrols.
        r = await c.post(f"/api/v1/programmes/{ids['msc']}/modules", headers=h, json={
            "code": "ONC501", "title": "Cancer Biology", "credits": 30, "level": 7, "isCore": True})
        assert r.status_code == 201, r.text
        ids["module"] = r.json()["id"]
        r = await c.post(f"/api/v1/programmes/{ids['other']}/modules", headers=h, json={
            "code": "NEU501", "title": "Neuroanatomy", "credits": 30, "level": 7, "isCore": True})
        ids["foreign_module"] = r.json()["id"]
        r = await c.post("/api/v1/students/enrol", headers=h, json={
            "person": {"givenName": "Mo", "familyName": "Dule"}, "programmeId": ids["msc"], "startDate": START})
        assert r.status_code == 201, r.text
        ids["student"] = r.json()["id"]
        yield c, h, ids, sm
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.fixture
def clock(monkeypatch):
    state = {"today": date(2027, 3, 1)}
    monkeypatch.setattr(fact_history, "today", lambda: state["today"])
    return state


async def _enrolment(c, h, sid):
    r = await c.get(f"/api/v1/students/{sid}/module-enrolments", headers=h)
    assert r.status_code == 200, r.text
    return r.json()[0]


async def _history(c, h, eid):
    r = await c.get(f"/api/v1/module-enrolments/{eid}/status-history", headers=h)
    assert r.status_code == 200, r.text
    return [(x["status"], x["validFrom"], x["validTo"]) for x in r.json()]


async def test_auto_enrolment_gets_the_students_own_dates(ctx, clock):
    c, h, ids, _ = ctx
    e = await _enrolment(c, h, ids["student"])
    assert e["academicYear"] == "2026/27"
    assert (e["startDate"], e["endDate"]) == (START, "2027-07-31")   # joined after 1 Aug
    assert await _history(c, h, e["id"]) == [("enrolled", START, None)]


async def test_withdrawal_ends_the_module_on_that_date(ctx, clock):
    c, h, ids, _ = ctx
    e = await _enrolment(c, h, ids["student"])
    r = await c.post(f"/api/v1/module-enrolments/{e['id']}/withdraw", headers=h,
                     json={"effectiveDate": "2027-01-15", "reason": "Left the module"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "withdrawn" and r.json()["endDate"] == "2027-01-15"
    assert await _history(c, h, e["id"]) == [
        ("enrolled", START, "2027-01-15"), ("withdrawn", "2027-01-15", None)]
    # A withdrawal needs a reason.
    r = await c.post(f"/api/v1/module-enrolments/{e['id']}/withdraw", headers=h,
                     json={"effectiveDate": "2027-02-01", "reason": " "})
    assert r.status_code == 422, r.text


async def test_future_dated_status_waits_for_its_day(ctx, clock):
    c, h, ids, sm = ctx
    clock["today"] = date(2026, 10, 1)
    e = await _enrolment(c, h, ids["student"])
    r = await c.patch(f"/api/v1/module-enrolments/{e['id']}/status", headers=h,
                      json={"status": "withdrawn", "effectiveDate": "2026-12-01", "reason": "Planned exit"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "enrolled"           # not yet
    clock["today"] = date(2026, 12, 2)
    async with sm() as s:
        assert await ModuleStatusHistoryService(s).refresh_due() == 1
        await s.commit()
    assert (await _enrolment(c, h, ids["student"]))["status"] == "withdrawn"


async def test_dates_must_sit_in_the_programme_period(ctx, clock):
    c, h, ids, _ = ctx
    e = await _enrolment(c, h, ids["student"])
    url = f"/api/v1/module-enrolments/{e['id']}/dates"
    # A late joiner: moving the start moves the start of the status history too.
    r = await c.patch(url, headers=h, json={"startDate": "2026-10-05", "reason": "Joined late"})
    assert r.status_code == 200, r.text
    assert r.json()["startDate"] == "2026-10-05"
    assert await _history(c, h, e["id"]) == [("enrolled", "2026-10-05", None)]
    # Before the student was on the programme.
    r = await c.patch(url, headers=h, json={"startDate": "2026-09-01", "reason": "x"})
    assert r.status_code == 422, r.text
    # End before start.
    r = await c.patch(url, headers=h, json={"endDate": "2026-10-01", "reason": "x"})
    assert r.status_code == 422, r.text
    # A reason is required.
    r = await c.patch(url, headers=h, json={"endDate": "2027-06-30", "reason": ""})
    assert r.status_code == 422, r.text


async def test_explicit_dates_on_a_module_the_programme_does_not_offer(ctx, clock):
    c, h, ids, _ = ctx
    r = await c.post(f"/api/v1/students/{ids['student']}/module-enrolments", headers=h, json={
        "moduleId": ids["foreign_module"], "academicYear": "2026/27", "startDate": "2026-10-01"})
    assert r.status_code == 422, r.text
    assert "MSC-NEU" in r.text


async def test_suspension_proposes_and_interrupts_open_modules(ctx, clock):
    c, h, ids, _ = ctx
    sid = ids["student"]
    e = await _enrolment(c, h, sid)
    r = await c.post(f"/api/v1/students/{sid}/lifecycle-events", headers=h, json={
        "eventType": "suspension", "reason": "Medical", "startDate": "2027-01-10", "endDate": "2027-04-10"})
    assert r.status_code == 201, r.text
    r = await c.post(f"/api/v1/lifecycle-events/{r.json()['id']}/approve", headers=h, json={})
    assert r.status_code == 200, r.text
    proposal = r.json()["moduleProposal"]
    assert proposal["effectiveDate"] == "2027-01-10"
    assert [m["moduleCode"] for m in proposal["modules"]] == ["ONC501"]

    # Nothing changes until the registry confirms.
    assert (await _enrolment(c, h, sid))["status"] == "enrolled"
    r = await c.post(f"/api/v1/students/{sid}/module-enrolments/interrupt", headers=h, json={
        "effectiveDate": proposal["effectiveDate"], "enrolmentIds": [m["enrolmentId"] for m in proposal["modules"]],
        "reason": "Suspended", "sourceEventId": proposal["sourceEventId"]})
    assert r.status_code == 200, r.text
    assert r.json()[0]["status"] == "interrupted" and r.json()[0]["endDate"] == "2027-01-10"
    assert (await c.get(f"/api/v1/students/{sid}/open-modules", headers=h)).json() == []

    # An enrolment that isn't open can't be interrupted.
    r = await c.post(f"/api/v1/students/{sid}/module-enrolments/interrupt", headers=h, json={
        "effectiveDate": "2027-01-10", "enrolmentIds": [e["id"]], "reason": "again"})
    assert r.status_code == 422, r.text


async def test_backfill_dates_older_enrolments(ctx, clock):
    c, h, ids, sm = ctx
    async with sm() as s:
        # An enrolment created before module dates existed: no dates, no history.
        e = ModuleEnrolment(student_id=uuid.UUID(ids["student"]), module_id=uuid.UUID(ids["module"]),
                            academic_year="2027/28", status=ModuleEnrolmentStatus.completed)
        s.add(e); await s.commit()
        eid = e.id
    async with sm.kw["bind"].begin() as conn:
        result = await conn.run_sync(lambda cn: backfill_module_enrolments(cn, today=date(2028, 9, 1)))
        assert result == {"enrolmentsDated": 1, "historyRows": 1}
        assert await conn.run_sync(lambda cn: check_module_enrolments(cn, today=date(2028, 9, 1))) == []
    async with sm() as s:
        e = await s.get(ModuleEnrolment, eid)
        assert (e.start_date, e.end_date) == (date(2027, 8, 1), date(2028, 7, 31))
        rows = (await s.execute(select(ModuleEnrolmentStatusHistory)
                                .where(ModuleEnrolmentStatusHistory.module_enrolment_id == eid))).scalars().all()
        assert [(r.status, r.valid_from, r.origin) for r in rows] == [
            (ModuleEnrolmentStatus.completed, date(2027, 8, 1), "backfill")]
