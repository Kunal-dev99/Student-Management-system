"""ICR G4 — study intensity (FTE %) tracked over time.

ICR needs a student's activity as a dated percentage, an end date driven by the real ratio, and a
per-year FTE for HESA. What must hold:
- an approved intensity change rescales the remaining time by the true ratio (50% doubles it)
- study mode stays a derived summary (100 = full-time, else part-time) and current % is exposed
- the intensity timeline is queryable as dated periods
- speeding back up shortens the remaining time
- fte_for_year is the time-weighted average over the academic year (HESA STULOAD)
"""
from __future__ import annotations

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
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.lifecycle import LifecycleService
from app.modules.student_record.models import Programme, Student

START = date(2026, 1, 1)
END = date(2030, 1, 1)  # 4-year full-time baseline


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
        person = Person(given_name="Sam", family_name="Rao"); s.add(person); await s.flush()
        student = Student(
            person_id=person.id, student_ref="PGR-INT", programme_id=prog.id,
            start_date=START, expected_end_date=END, original_expected_end_date=END,
            study_mode=StudyMode.full_time, status=StudentStatus.active,
        )
        s.add(student); await s.flush()
        ids["student"] = str(student.id)
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


async def _request_intensity(c, h, sid, pct, start="2027-01-01"):
    return await c.post(f"/api/v1/students/{sid}/lifecycle-events", headers=h, json={
        "eventType": "intensity_change", "reason": "Clinical duties", "startDate": start,
        "intensityPct": pct,
    })


async def _approve(c, h, event_id):
    return await c.post(f"/api/v1/lifecycle-events/{event_id}/approve", headers=h, json={})


@pytest.mark.asyncio
async def test_dropping_to_50pct_doubles_remaining_time(ctx):
    c, h, ids, _ = ctx
    sid = ids["student"]
    req = await _request_intensity(c, h, sid, 50)
    assert req.status_code == 201, req.text
    assert req.json()["status"] == "requested"  # request alone changes nothing

    res = await _approve(c, h, req.json()["id"])
    assert res.status_code == 200, res.text
    recalc = res.json()["recalculation"]
    remaining = (END - date(2027, 1, 1)).days
    assert recalc["totalDaysApplied"] == remaining  # 100/50 - 1 = 1 -> +remaining

    summary = (await c.get(f"/api/v1/students/{sid}/summary", headers=h)).json()
    assert summary["currentIntensityPct"] == 50
    assert summary["studyMode"] == "part_time"


@pytest.mark.asyncio
async def test_intensity_timeline(ctx):
    c, h, ids, _ = ctx
    sid = ids["student"]
    req = await _request_intensity(c, h, sid, 60)
    await _approve(c, h, req.json()["id"])
    overview = (await c.get(f"/api/v1/students/{sid}/intensity", headers=h)).json()
    assert overview["currentPct"] == 60
    # A 100% period up to the change, then a 60% period after.
    pcts = [p["pct"] for p in overview["periods"]]
    assert pcts[0] == 100 and pcts[-1] == 60
    assert overview["periods"][0]["from"] == "2026-01-01"
    assert overview["periods"][0]["to"] == "2027-01-01"


@pytest.mark.asyncio
async def test_speeding_back_up_shortens(ctx):
    c, h, ids, _ = ctx
    sid = ids["student"]
    # 100 -> 50 (extends), then 50 -> 100 (should remove time).
    r1 = await _request_intensity(c, h, sid, 50, start="2027-01-01")
    await _approve(c, h, r1.json()["id"])
    r2 = await _request_intensity(c, h, sid, 100, start="2028-01-01")
    res2 = await _approve(c, h, r2.json()["id"])
    assert res2.status_code == 200, res2.text
    # The 50->100 event contributes negative days.
    ev = res2.json()["event"]
    assert ev["daysApplied"] < 0
    assert ev["previousIntensityPct"] == 50 and ev["intensityPct"] == 100


@pytest.mark.asyncio
async def test_fte_for_year_is_time_weighted(ctx):
    c, h, ids, sm = ctx
    sid = ids["student"]
    # Drop to 50% halfway through the 2026/27 academic year (Aug start): 1 Feb 2027.
    req = await _request_intensity(c, h, sid, 50, start="2027-02-01")
    await _approve(c, h, req.json()["id"])
    async with sm() as s:
        import uuid as _uuid
        student = (await s.execute(select(Student).where(Student.id == _uuid.UUID(sid)))).scalar_one()
        # Academic year 2026 = 1 Aug 2026 .. 31 Jul 2027. 100% for Aug–Jan, 50% for Feb–Jul.
        fte = await LifecycleService(s).fte_for_year(student, year=2026, start_month=8)
        assert fte is not None
        assert 70 <= fte <= 80  # roughly half the year at 100, half at 50 -> ~75


@pytest.mark.asyncio
async def test_intensity_must_be_in_range_and_differ(ctx):
    c, h, ids, _ = ctx
    sid = ids["student"]
    bad = await _request_intensity(c, h, sid, 0)
    assert bad.status_code in (400, 422)
    same = await _request_intensity(c, h, sid, 100)  # already full-time
    assert same.status_code in (400, 422)
