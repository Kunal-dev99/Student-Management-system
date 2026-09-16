"""ICR G1 (full academic model) — module results, resit caps, condonement, grading policy.

Drives the real taught endpoints: configure a module + assessment, enrol, record marks, and check
the module RESULT (mark, outcome, credits) plus the capped-resit and board-condonement rules and
per-programme grading policy behave correctly.
"""
from __future__ import annotations

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
from app.modules.student_record.constants import ProgrammeType
from app.modules.student_record.models import Programme


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
        u = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]
        prog = Programme(name="MSc Test", code="MSC-T", programme_type=ProgrammeType.taught,
                         taught_total_credits=180)
        s.add(prog); await s.flush(); ids["programme"] = str(prog.id)
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
        yield c, h, ids
    app.dependency_overrides.clear()
    await eng.dispose()


async def _module(c, h, pid, *, credits=30, level=7, is_core=True):
    r = await c.post(f"/api/v1/programmes/{pid}/modules", headers=h, json={
        "code": "M1", "title": "Module 1", "credits": credits, "level": level, "isCore": is_core,
    })
    assert r.status_code == 201, r.text
    return r.json()


async def _assessment(c, h, mid, *, pass_mark=50, resit_cap=50, resit_allowed=True):
    r = await c.post(f"/api/v1/taught-modules/{mid}/assessments", headers=h, json={
        "title": "Exam", "assessmentType": "exam", "weightPct": 100, "maxMark": 100,
        "passMark": pass_mark, "resitAllowed": resit_allowed, "resitCap": resit_cap,
    })
    assert r.status_code == 201, r.text
    return r.json()


async def _enrol_student(c, h, pid):
    r = await c.post("/api/v1/students/enrol", headers=h, json={
        "person": {"givenName": "Taught", "familyName": "Student"}, "programmeId": pid,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _enrol_module(c, h, sid, mid):
    r = await c.post(f"/api/v1/students/{sid}/module-enrolments", headers=h,
                     json={"moduleId": mid, "academicYear": "2026/27"})
    assert r.status_code == 201, r.text
    return r.json()


async def _record(c, h, eid, aid, mark, *, is_resit=False):
    r = await c.post(f"/api/v1/module-enrolments/{eid}/results", headers=h,
                     json={"assessmentId": aid, "mark": mark, "isResit": is_resit})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_module_level_and_core_persist(ctx):
    c, h, ids = ctx
    m = await _module(c, h, ids["programme"], level=7, is_core=False)
    assert m["level"] == 7 and m["isCore"] is False


@pytest.mark.asyncio
async def test_fail_then_capped_resit_passes_the_module(ctx):
    c, h, ids = ctx
    pid = ids["programme"]
    m = await _module(c, h, pid, credits=30)
    a = await _assessment(c, h, m["id"], pass_mark=50, resit_cap=50)
    sid = await _enrol_student(c, h, pid)
    enr = await _enrol_module(c, h, sid, m["id"])

    # First sit 45 -> module fails, no credits.
    e = await _record(c, h, enr["id"], a["id"], 45)
    assert float(e["moduleMark"]) == 45
    assert e["outcome"] == "failed" and e["creditsAwarded"] == 0

    # Resit scored 72 -> capped to 50; module now passes and awards its credits.
    e = await _record(c, h, enr["id"], a["id"], 72, is_resit=True)
    resit = next(r for r in e["results"] if r["isResit"])
    assert float(resit["mark"]) == 50 and resit["capped"] is True and resit["attemptNumber"] == 2
    assert float(e["moduleMark"]) == 50
    assert e["outcome"] == "passed" and e["creditsAwarded"] == 30


@pytest.mark.asyncio
async def test_condone_a_failed_module_awards_its_credits(ctx):
    c, h, ids = ctx
    pid = ids["programme"]
    m = await _module(c, h, pid, credits=30)
    a = await _assessment(c, h, m["id"], pass_mark=50, resit_cap=None, resit_allowed=False)
    sid = await _enrol_student(c, h, pid)
    enr = await _enrol_module(c, h, sid, m["id"])
    e = await _record(c, h, enr["id"], a["id"], 40)
    assert e["outcome"] == "failed" and e["creditsAwarded"] == 0

    con = await c.patch(f"/api/v1/module-enrolments/{enr['id']}/condone", headers=h,
                        json={"condoned": True})
    assert con.status_code == 200, con.text
    assert con.json()["outcome"] == "condoned" and con.json()["creditsAwarded"] == 30
    assert con.json()["condoned"] is True


@pytest.mark.asyncio
async def test_grading_policy_override_changes_classification(ctx):
    c, h, ids = ctx
    pid = ids["programme"]
    # Raise the distinction cut-off to 80 for this programme.
    await c.patch(f"/api/v1/programmes/{pid}", headers=h,
                  json={"gradingPolicy": {"distinctionMark": 80, "meritMark": 60, "passMarkAward": 50}})
    m = await _module(c, h, pid, credits=30)
    a = await _assessment(c, h, m["id"])
    sid = await _enrol_student(c, h, pid)
    enr = await _enrol_module(c, h, sid, m["id"])
    await _record(c, h, enr["id"], a["id"], 75)  # would be a distinction under the default 70

    award = await c.post(f"/api/v1/students/{sid}/taught-award", headers=h)
    assert award.status_code == 200, award.text
    # 75 is a merit here (>=60, <80), not a distinction.
    assert award.json()["classification"] == "merit"


@pytest.mark.asyncio
async def test_dissertation_second_marker_persists(ctx):
    c, h, ids = ctx
    pid = ids["programme"]
    sid = await _enrol_student(c, h, pid)
    r = await c.put(f"/api/v1/students/{sid}/dissertation", headers=h, json={
        "title": "A dissertation", "firstMark": 68, "secondMark": 64, "mark": 66, "wordCount": 15000,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert float(d["firstMark"]) == 68 and float(d["secondMark"]) == 64 and float(d["mark"]) == 66
    assert d["wordCount"] == 15000
