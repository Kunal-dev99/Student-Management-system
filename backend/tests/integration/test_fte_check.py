"""Demo 2 item 1.5 — a student's FTE must not exceed the sum of their module FTE in the year.

Configurable (statutory.fte_check off / warn / stop, a tolerance, research students opt-in), and
checked in two places from one rule: the statutory return's validation and the approval of an
intensity change.

Fixture: a full-time (100%) MSc student on a 180-credit programme taking two 60-credit modules
(33.33% each) plus a withdrawn one that doesn't count, so their module FTE is 66.66%; and a PhD
student with one module.
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
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.settings.models import InstitutionSetting
from app.modules.student_record import fte_check
from app.modules.student_record.constants import ProgrammeType, StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student
from app.modules.taught.constants import ModuleEnrolmentStatus
from app.modules.taught.models import ModuleEnrolment, TaughtModule

YEAR = "2026/27"


def test_rule():
    warn = fte_check.FteCheckPolicy("warn")
    assert fte_check.evaluate(100, 66.67, warn, is_research=False)
    assert fte_check.evaluate(100, 100, warn, is_research=False) is None           # equal is fine
    assert fte_check.evaluate(100, 95, fte_check.FteCheckPolicy("warn", 5), is_research=False) is None
    assert fte_check.evaluate(100, 94, fte_check.FteCheckPolicy("warn", 5), is_research=False)
    assert fte_check.evaluate(100, 66.67, fte_check.FteCheckPolicy("off"), is_research=False) is None
    assert fte_check.evaluate(100, None, warn, is_research=False) is None           # no modules yet
    assert fte_check.evaluate(100, 10, warn, is_research=True) is None              # research skipped
    assert fte_check.evaluate(100, 10, fte_check.FteCheckPolicy("warn", 0, True), is_research=True)
    assert fte_check.academic_year_of(date(2026, 8, 1)) == "2026/27"
    assert fte_check.academic_year_of(date(2027, 7, 31)) == "2026/27"
    assert fte_check.module_fte_total([{"ftePct": 50, "status": "enrolled"},
                                       {"ftePct": 50, "status": "withdrawn"}]) == 50


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    ids = {}
    async with sm() as s:
        perms = [Permission(code=c) for c in PERMISSIONS]
        s.add_all(perms); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = perms
        user = User(email="a@inst.example.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]
        msc = Programme(name="MSc Data", code="MSC-DATA", programme_type=ProgrammeType.taught,
                        taught_total_credits=180)
        phd = Programme(name="PhD CS", code="PHD-CS")
        s.add_all([msc, phd]); await s.flush()
        mods = [TaughtModule(programme_id=msc.id, code=f"M{i}", title=f"Module {i}", credits=60) for i in range(3)]
        s.add_all(mods); await s.flush()
        for ref, prog in (("MSC-1", msc), ("PHD-1", phd)):
            person = Person(given_name="S", family_name=ref); s.add(person); await s.flush()
            st = Student(person_id=person.id, student_ref=ref, programme_id=prog.id,
                         start_date=date(2026, 9, 1), expected_end_date=date(2027, 9, 30),
                         original_expected_end_date=date(2027, 9, 30),
                         study_mode=StudyMode.full_time, status=StudentStatus.active)
            s.add(st); await s.flush()
            ids[ref] = str(st.id)
            enrol = mods if prog is msc else mods[:1]
            for i, m in enumerate(enrol):
                s.add(ModuleEnrolment(student_id=st.id, module_id=m.id, academic_year=YEAR,
                                      status=ModuleEnrolmentStatus.withdrawn if i == 2
                                      else ModuleEnrolmentStatus.enrolled))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@inst.example.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        pid = (await c.post("/api/v1/report-profiles", headers=h, json={
            "code": "HESA_STUDENT", "name": "HESA Student Return", "academicYear": YEAR})).json()["id"]
        await c.post(f"/api/v1/report-profiles/{pid}/fields", headers=h,
                     json={"targetField": "OWNSTU", "sourceExpression": "student.ref"})
        yield c, h, pid, ids, sm
    app.dependency_overrides.clear()
    await eng.dispose()


async def _set(sm, **values):
    async with sm() as s:
        for key, value in values.items():
            s.add(InstitutionSetting(key=f"statutory.{key}", value={"value": value}))
        await s.commit()


async def _fte_issues(c, h, pid):
    gen = (await c.post(f"/api/v1/report-profiles/{pid}/generate", headers=h)).json()
    v = gen["validation"]
    return [i for i in v["issues"] if i.get("ruleKey") == "fte_vs_module_fte"], v


@pytest.mark.asyncio
async def test_return_warns_by_default_and_skips_research(ctx):
    c, h, pid, _, _ = ctx
    issues, v = await _fte_issues(c, h, pid)
    assert [(i["studentRef"], i["severity"]) for i in issues] == [("MSC-1", "warning")]
    assert "66.66%" in issues[0]["message"]          # the withdrawn module isn't counted
    assert v["valid"] is True                        # a warning doesn't block sign-off


@pytest.mark.asyncio
async def test_stop_mode_is_an_error_that_blocks_sign_off(ctx):
    c, h, pid, _, sm = ctx
    await _set(sm, fte_check="stop")
    issues, v = await _fte_issues(c, h, pid)
    assert [i["severity"] for i in issues] == ["error"] and v["valid"] is False


@pytest.mark.asyncio
async def test_off_tolerance_and_research_opt_in(ctx):
    c, h, pid, _, sm = ctx
    await _set(sm, fte_check_tolerance=40.0, fte_check_research=True)
    issues, _ = await _fte_issues(c, h, pid)
    # MSc is within 40 points (66.66 + 40 >= 100); the PhD (33.33%) is now checked and isn't.
    assert [i["studentRef"] for i in issues] == ["PHD-1"]
    async with sm() as s:
        s.add(InstitutionSetting(key="statutory.fte_check", value={"value": "off"}))
        await s.commit()
    assert (await _fte_issues(c, h, pid))[0] == []


async def _intensity(c, h, sid, pct):
    r = await c.post(f"/api/v1/students/{sid}/lifecycle-events", headers=h, json={
        "eventType": "intensity_change", "reason": "Workload", "startDate": "2026-11-01", "intensityPct": pct})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_intensity_approval_warns_or_refuses(ctx):
    c, h, _, ids, sm = ctx
    sid = ids["MSC-1"]
    ok = await c.post(f"/api/v1/lifecycle-events/{await _intensity(c, h, sid, 90)}/approve", headers=h, json={})
    assert ok.status_code == 200, ok.text
    assert "66.66%" in ok.json()["warnings"][0]      # warn: approved, flagged

    await _set(sm, fte_check="stop")
    eid = await _intensity(c, h, sid, 80)
    refused = await c.post(f"/api/v1/lifecycle-events/{eid}/approve", headers=h, json={})
    assert refused.status_code == 409 and "Not approved" in refused.text
    events = (await c.get(f"/api/v1/students/{sid}/lifecycle-events", headers=h)).json()
    assert next(e for e in events if e["id"] == eid)["status"] == "requested"   # nothing changed

    within = await c.post(f"/api/v1/lifecycle-events/{await _intensity(c, h, sid, 60)}/approve",
                          headers=h, json={})
    assert within.status_code == 200 and "warnings" not in within.json()

    # A research student isn't checked by default, even in stop mode.
    phd = await c.post(f"/api/v1/lifecycle-events/{await _intensity(c, h, ids['PHD-1'], 90)}/approve",
                       headers=h, json={})
    assert phd.status_code == 200, phd.text
