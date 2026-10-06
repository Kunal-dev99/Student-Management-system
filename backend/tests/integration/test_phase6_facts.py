"""Effective dating, Phase 6 — fee status, study location and opt-in custom attribute history.

What must hold:
- fee status and location have no history until first recorded; a value opens it from its date,
  later values close the earlier one, and the cached value follows today's period
- values are validated, and can't precede the student's start
- a custom attribute with history on records dated values (no clearing); switching history on
  keeps existing values from the student's start; attributes without it still overwrite
- the return reads all three as at the record's date; the history tab, as-of view and
  changes-since-sign-off include them
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.errors import WorkflowError
from app.db.base import Base
from app.main import app  # noqa: F401  registers every model
from app.modules.exports.models import ReportProfile
from app.modules.exports.statutory import StatutoryEngine
from app.modules.person.models import Person
from app.modules.student_record import fact_history
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.custom_fields import CustomFieldService
from app.modules.student_record.fact_history import (
    FeeStatusHistoryService,
    LocationHistoryService,
    initialise_all,
)
from app.modules.student_record.models import Programme, Student
from app.modules.student_record.retrospective import changes_since_signoff
from app.modules.student_record.timeline import StudentTimeline

START = date(2025, 10, 1)


async def _live_field(s, *, label, data_type, reason, user_id=None, track_history=False):
    """An attribute that has already been through request → approve → activate (that flow is
    covered by test_custom_attr_governance_p1); these tests are about its dated values."""
    from app.modules.student_record.custom_fields import slugify
    from app.modules.student_record.models import StudentCustomField

    f = StudentCustomField(key=slugify(label), label=label, data_type=data_type, reason=reason,
                           created_by_user_id=user_id, track_history=track_history, status="active")
    s.add(f)
    await s.commit()
    return f


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        prog = Programme(name="PhD Oncology", code="PHD"); s.add(prog)
        person = Person(given_name="Ana", family_name="Lee"); s.add(person); await s.flush()
        st = Student(person_id=person.id, student_ref="PGR-ED6", programme_id=prog.id,
                     start_date=START, expected_end_date=date(2029, 9, 30),
                     study_mode=StudyMode.full_time, status=StudentStatus.active)
        s.add(st); await s.flush()
        await initialise_all(s, st)
        await s.commit()
        sid = st.id
    yield sid, sm
    await eng.dispose()


@pytest.fixture
def clock(monkeypatch):
    state = {"today": date(2026, 10, 1)}
    monkeypatch.setattr(fact_history, "today", lambda: state["today"])
    return state


# --------------------------------------------------------------------------------------
# Fee status and location
# --------------------------------------------------------------------------------------

async def test_fee_status_opens_on_first_value_and_follows_today(ctx, clock):
    sid, sm = ctx
    async with sm() as s:
        st = await s.get(Student, sid)
        fee = FeeStatusHistoryService(s)
        assert await fee.live_rows(sid) == [] and st.fee_status is None   # nothing yet
        await fee.change(st, "overseas", effective_from=START)
        await fee.change(st, "home", effective_from=date(2026, 3, 1))     # settled status
        await fee.change(st, "unknown", effective_from=date(2026, 12, 1)) # future: waits
        await s.commit()
        rows = [(r.fee_status, r.valid_from, r.valid_to) for r in await fee.live_rows(sid)]
        assert rows == [("overseas", START, date(2026, 3, 1)), ("home", date(2026, 3, 1), date(2026, 12, 1)),
                        ("unknown", date(2026, 12, 1), None)]
        assert st.fee_status == "home"
        clock["today"] = date(2026, 12, 2)
        assert await fee.refresh_due() == 1 and st.fee_status == "unknown"


async def test_values_are_validated(ctx, clock):
    sid, sm = ctx
    async with sm() as s:
        st = await s.get(Student, sid)
        with pytest.raises(WorkflowError, match="Fee status must be one of"):
            FeeStatusHistoryService.validate("eu")
        with pytest.raises(WorkflowError, match="study location is required"):
            LocationHistoryService.validate("  ")
        with pytest.raises(WorkflowError, match="start date"):
            await LocationHistoryService(s).change(st, "LONDON", effective_from=date(2025, 1, 1))


# --------------------------------------------------------------------------------------
# Custom attribute history
# --------------------------------------------------------------------------------------

async def test_custom_attribute_history_opt_in(ctx, clock):
    sid, sm = ctx
    async with sm() as s:
        svc = CustomFieldService(s)
        plain = await _live_field(s, label="Notes code", data_type="code", reason="one-off", user_id=None)
        await svc.set_values(plain.id, entries=[{"studentId": str(sid), "value": "A"}], user_id=None)
        await svc.set_values(plain.id, entries=[{"studentId": str(sid), "value": "B"}], user_id=None)

        dated = await _live_field(s, label="Research council", data_type="code",
                                       reason="HESA needs it as at the year end", user_id=None)
        await svc.set_values(dated.id, entries=[{"studentId": str(sid), "value": "MRC"}], user_id=None)
        field = await svc.enable_history(dated.id, user_id=None)
        assert field.track_history is True
        # The existing value is kept from the student's start, marked as rebuilt.
        await svc.set_values(dated.id, entries=[{"studentId": str(sid), "value": "CRUK"}], user_id=None,
                             effective_date=date(2026, 4, 1))
        with pytest.raises(WorkflowError, match="can't be cleared"):
            await svc.set_values(dated.id, entries=[{"studentId": str(sid), "value": ""}], user_id=None)
        with pytest.raises(WorkflowError, match="start date"):
            await svc.set_values(dated.id, entries=[{"studentId": str(sid), "value": "X"}], user_id=None,
                                 effective_date=date(2025, 1, 1))

    async with sm() as s:
        h = await StudentTimeline(s).history(sid)
    custom = [(e["value"], e["validFrom"], e["validTo"], e["origin"]) for e in h["entries"] if e["fact"] == "custom"]
    assert custom == [("MRC", "2025-10-01", "2026-04-01", "backfill"), ("CRUK", "2026-04-01", None, "change")]
    async with sm() as s:
        values = {r["studentId"]: r["value"] for r in await CustomFieldService(s).field_values(plain.id)}
    assert values[str(sid)] == "B"   # untracked attribute simply overwrites


# --------------------------------------------------------------------------------------
# The return, history tab, as-of and changes since sign-off
# --------------------------------------------------------------------------------------

async def test_return_and_views_read_the_new_facts_as_at_the_date(ctx, clock):
    sid, sm = ctx
    async with sm() as s:
        st = await s.get(Student, sid)
        await FeeStatusHistoryService(s).change(st, "overseas", effective_from=START)
        await FeeStatusHistoryService(s).change(st, "home", effective_from=date(2026, 9, 1))  # next year
        await LocationHistoryService(s).change(st, "SUTTON", effective_from=date(2026, 2, 1))
        svc = CustomFieldService(s)
        f = await _live_field(s, label="Research council", data_type="code", reason="HESA",
                                   user_id=None, track_history=True)
        await svc.set_values(f.id, entries=[{"studentId": str(sid), "value": "MRC"}], user_id=None,
                             effective_date=START)
        await svc.set_values(f.id, entries=[{"studentId": str(sid), "value": "CRUK"}], user_id=None,
                             effective_date=date(2026, 9, 1))
        s.add(ReportProfile(code="HESA_STUDENT", name="HESA Student", academic_year="2025/26",
                            signed_off_at=datetime.now(timezone.utc) - timedelta(days=1)))
        await s.commit()

    async with sm() as s:
        [rec] = [r for r in await StatutoryEngine(s).build_records("2025/26") if r["student"]["ref"] == "PGR-ED6"]
    # As at 31 Jul 2026: the 2026/27 values don't leak back into 2025/26.
    assert rec["student"]["feeStatus"] == "overseas"
    assert rec["student"]["studyLocation"] == "SUTTON"
    assert rec["custom"]["research_council"] == "MRC"

    async with sm() as s:
        tl = StudentTimeline(s)
        facts = {e["fact"] for e in (await tl.history(sid))["entries"]}
        then = await tl.as_of(sid, date(2026, 3, 1))
        out = await changes_since_signoff(s, (await s.execute(
            ReportProfile.__table__.select())).first().id)
    assert {"fee_status", "location", "custom"} <= facts
    assert (then["feeStatus"], then["studyLocation"]) == ("overseas", "SUTTON")
    assert then["custom"] == [{"key": "research_council", "label": "Research council", "value": "MRC"}]
    changed = {c["fact"] for st_ in out["students"] for c in st_["changes"]}
    assert {"fee_status", "location", "custom"} <= changed


# --------------------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------------------

async def test_http_record_fact_and_dated_custom_values(ctx, clock):
    from httpx import ASGITransport, AsyncClient

    from app.core.security import hash_password
    from app.db.session import get_session
    from app.main import app as fastapi_app
    from app.modules.identity.models import Permission, Role, User

    sid, sm = ctx
    async with sm() as s:
        perms = [Permission(code=c) for c in ("student.read", "student.write", "admin.configure",
                                               "custom_attribute.request", "custom_attribute.approve")]
        s.add_all(perms); await s.flush()
        role = Role(name="Registry"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = perms
        for email in ("r@t.com", "chk@t.com"):   # maker + checker
            user = User(email=email, password_hash=hash_password("pw"), is_active=True)
            s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    fastapi_app.dependency_overrides[get_session] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as c:
            tok = (await c.post("/api/v1/auth/login", json={"email": "r@t.com", "password": "pw"})).json()
            h = {"Authorization": f"Bearer {tok['accessToken']}"}
            r = await c.post(f"/api/v1/students/{sid}/facts/fee-status", headers=h,
                             json={"value": "Home", "effectiveDate": "2025-10-01", "reason": "Settled"})
            assert r.status_code == 200, r.text
            assert r.json()["current"] == "home" and r.json()["row"]["feeStatus"] == "home"
            r = await c.post(f"/api/v1/students/{sid}/facts/fee-status", headers=h, json={"value": "eu"})
            assert r.status_code in (409, 422), r.text
            assert (await c.post(f"/api/v1/students/{sid}/facts/shoe-size", headers=h,
                                 json={"value": "9"})).status_code == 404
            hist = (await c.get(f"/api/v1/students/{sid}/facts/fee-status", headers=h)).json()
            assert [x["feeStatus"] for x in hist] == ["home"]
            assert (await c.get(f"/api/v1/students/{sid}", headers=h)).json()["feeStatus"] == "home"

            from tests.integration.custom_attr_helpers import live_attribute
            tok2 = (await c.post("/api/v1/auth/login", json={"email": "chk@t.com", "password": "pw"})).json()
            h2 = {"Authorization": f"Bearer {tok2['accessToken']}"}
            f = await live_attribute(c, h, h2, label="Research council", dataType="code", reason="HESA",
                                     trackHistory=True)
            assert f["trackHistory"] is True
            r = await c.put(f"/api/v1/students/custom-fields/{f['id']}/values", headers=h, json={
                "effectiveDate": "2026-01-01", "values": [{"studentId": str(sid), "value": "MRC"}]})
            assert r.status_code == 200, r.text
            plain = await live_attribute(c, h, h2, label="Desk", dataType="string", reason="ops")
            r = await c.post(f"/api/v1/students/custom-fields/{plain['id']}/track-history", headers=h)
            assert r.status_code == 200 and r.json()["trackHistory"] is True
    finally:
        fastapi_app.dependency_overrides.clear()
