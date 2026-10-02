"""Effective dating, Phase 10 — HESA Engagement (and Leaver).

What must hold:
- the expected end date is dated: an extension records the new expectation from the day it is
  approved, and a return reports the expected end held on its date
- fee eligibility and "primarily outside the UK" are dated Engagement facts; study intention and
  incoming exchange are plain Engagement fields
- a withdrawal carries a leaver reason; the return's Leaver gives when and why the engagement ended
- research-council funding in force makes the student a research council student, with the
  studentship reference
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
from app.modules.exports.statutory import StatutoryEngine
from app.modules.funding.constants import FundingType
from app.modules.funding.models import FundingArrangement
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record import fact_history
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.fact_history import ExpectedEndHistoryService, initialise_all
from app.modules.student_record.models import Programme, Student

START = date(2025, 10, 1)
END = date(2029, 9, 30)


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
        u = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]
        prog = Programme(name="PhD Oncology", code="PHD"); s.add(prog)
        person = Person(given_name="Ana", family_name="Lee"); s.add(person); await s.flush()
        st = Student(person_id=person.id, student_ref="PGR-ENG", programme_id=prog.id, start_date=START,
                     expected_end_date=END, original_expected_end_date=END,
                     study_mode=StudyMode.full_time, status=StudentStatus.active)
        s.add(st); await s.flush()
        await initialise_all(s, st, valid_from=START)
        s.add(FundingArrangement(student_id=st.id, funding_type=FundingType.research_council,
                                 valid_from=START, funder_reference="MR/X0001/1"))
        await s.commit()
        ids["student"] = str(st.id)

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        h = {"Authorization": "Bearer " + (await c.post("/api/v1/auth/login", json={
            "email": "a@t.com", "password": "pw"})).json()["accessToken"]}
        yield c, h, ids, sm
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.fixture
def clock(monkeypatch):
    state = {"today": date(2026, 9, 1)}
    monkeypatch.setattr(fact_history, "today", lambda: state["today"])
    return state


async def _record(sm, year="2025/26", **kw) -> dict:
    async with sm() as s:
        return [r for r in await StatutoryEngine(s).build_records(year, **kw)
                if r["student"]["ref"] == "PGR-ENG"][0]


async def _approve(c, h, sid, body):
    r = await c.post(f"/api/v1/students/{sid}/lifecycle-events", headers=h, json=body)
    assert r.status_code == 201, r.text
    r = await c.post(f"/api/v1/lifecycle-events/{r.json()['id']}/approve", headers=h, json={})
    assert r.status_code == 200, r.text
    return r


async def test_expected_end_is_dated(ctx, clock):
    c, h, ids, sm = ctx
    # Extension approved on 1 Sep 2026: the new expectation holds from that day.
    await _approve(c, h, ids["student"], {"eventType": "extension", "reason": "Lab closure",
                                         "startDate": "2026-09-01", "extensionDays": 90})
    async with sm() as s:
        rows = await ExpectedEndHistoryService(s).live_rows(__import__("uuid").UUID(ids["student"]))
    assert [(r.expected_end_date, r.valid_from, r.valid_to) for r in rows] == [
        (END, START, date(2026, 9, 1)), (date(2029, 12, 29), date(2026, 9, 1), None)]
    # The 2025/26 return holds the end expected during that year; 2026/27 the extended one.
    assert (await _record(sm))["engagement"]["expectedEndDate"] == END
    assert (await _record(sm, "2026/27"))["engagement"]["expectedEndDate"] == date(2029, 12, 29)


async def test_engagement_facts_and_fields(ctx, clock):
    c, h, ids, sm = ctx
    sid = ids["student"]
    r = await c.post(f"/api/v1/students/{sid}/facts/fee-eligibility", headers=h,
                     json={"value": "eligible", "effectiveDate": "2025-10-01"})
    assert r.status_code == 200, r.text
    r = await c.post(f"/api/v1/students/{sid}/facts/outside-uk", headers=h,
                     json={"value": "yes", "effectiveDate": "2026-02-01", "reason": "Fieldwork in Kenya"})
    assert r.status_code == 200, r.text
    r = await c.post(f"/api/v1/students/{sid}/facts/fee-eligibility", headers=h, json={"value": "maybe"})
    assert r.status_code in (409, 422)
    r = await c.patch(f"/api/v1/students/{sid}", headers=h,
                      json={"studyIntention": "doctorate", "incomingExchange": False})
    assert r.status_code == 200, r.text
    detail = (await c.get(f"/api/v1/students/{sid}", headers=h)).json()
    assert (detail["feeEligibility"], detail["primarilyOutsideUk"], detail["studyIntention"]) == (
        "eligible", True, "doctorate")

    early = (await _record(sm, as_at=date(2026, 1, 15)))["engagement"]
    late = (await _record(sm))["engagement"]
    assert (early["feeEligibility"], early["primarilyOutsideUk"]) == ("eligible", None)
    assert late["primarilyOutsideUk"] is True
    assert (late["numhus"], late["startDate"], late["studyIntention"], late["incomingExchange"]) == (
        "PGR-ENG", START, "doctorate", False)
    assert (late["researchCouncilStudent"], late["studentshipRef"]) == (True, "MR/X0001/1")


async def test_leaver_from_a_withdrawal(ctx, clock):
    c, h, ids, sm = ctx
    sid = ids["student"]
    r = await c.post(f"/api/v1/students/{sid}/lifecycle-events", headers=h, json={
        "eventType": "withdrawal", "reason": "Left", "startDate": "2026-05-01", "leaverReason": "nonsense"})
    assert r.status_code == 422
    r = await _approve(c, h, sid, {"eventType": "withdrawal", "reason": "Could not continue funding",
                                   "startDate": "2026-05-01", "leaverReason": "financial"})
    rec = await _record(sm)
    assert rec["leaver"] == {"endDate": date(2026, 5, 1), "status": "withdrawn", "reason": "financial"}
    # Before the withdrawal the engagement hadn't ended.
    assert (await _record(sm, as_at=date(2026, 3, 1)))["leaver"]["endDate"] is None
