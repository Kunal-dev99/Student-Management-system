"""Effective dating, Phase 9 — units of assessment, dated for students and supervisors.

What must hold:
- the UOA list is managed (code unique; a retired UOA can't be newly assigned)
- a student's UOA is a dated fact; the cache follows today's period
- a supervisor's UOA is dated on the person; one change applies to every student they supervise
- the return takes both as at the record's date (Alistair: a supervisor's UOA changed at the
  last minute must not rewrite a period before the change)
- a supervisor's UOA change recorded after sign-off is listed against their students
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.exports.models import ReportProfile
from app.modules.exports.statutory import StatutoryEngine
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record import fact_history
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.fact_history import initialise_all
from app.modules.student_record.models import Programme, Student
from app.modules.student_record.retrospective import changes_since_signoff
from app.modules.supervision.constants import SupervisionStatus, SupervisorRole
from app.modules.supervision.models import SupervisorRelationship

START = date(2025, 10, 1)


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
        sp = Person(given_name="Ana", family_name="Lee")
        dr = Person(given_name="Alice", family_name="Arden")
        s.add_all([sp, dr]); await s.flush()
        st = Student(person_id=sp.id, student_ref="PGR-UOA", programme_id=prog.id, start_date=START,
                     study_mode=StudyMode.full_time, status=StudentStatus.active)
        s.add(st); await s.flush()
        await initialise_all(s, st)
        s.add(SupervisorRelationship(student_id=st.id, supervisor_person_id=dr.id, role=SupervisorRole.primary,
                                     status=SupervisionStatus.active, valid_from=START))
        await s.commit()
        ids.update(student=str(st.id), dr=str(dr.id))

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        h = {"Authorization": "Bearer " + (await c.post("/api/v1/auth/login", json={
            "email": "a@t.com", "password": "pw"})).json()["accessToken"]}
        for code, name in (("1", "Clinical Medicine"), ("3", "Allied Health"), ("9", "Physics")):
            r = await c.post("/api/v1/units-of-assessment", headers=h, json={"code": code, "name": name, "panel": "A"})
            assert r.status_code == 201, r.text
            ids[f"uoa{code}"] = r.json()["id"]
        yield c, h, ids, sm
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.fixture
def clock(monkeypatch):
    state = {"today": date(2026, 10, 1)}
    monkeypatch.setattr(fact_history, "today", lambda: state["today"])
    return state


async def test_uoa_list_rules(ctx, clock):
    c, h, ids, _ = ctx
    r = await c.post("/api/v1/units-of-assessment", headers=h, json={"code": "1", "name": "Dup"})
    assert r.status_code == 409
    r = await c.patch(f"/api/v1/units-of-assessment/{ids['uoa9']}", headers=h, json={"isActive": False})
    assert r.status_code == 200 and r.json()["isActive"] is False
    r = await c.post(f"/api/v1/students/{ids['student']}/facts/uoa", headers=h,
                     json={"value": ids["uoa9"], "effectiveDate": "2026-09-01"})
    assert r.status_code == 422 and "no longer in use" in r.text
    assert [u["code"] for u in (await c.get("/api/v1/units-of-assessment", headers=h)).json()] == ["1", "3", "9"]


async def test_student_and_supervisor_uoa_are_dated(ctx, clock):
    c, h, ids, sm = ctx
    r = await c.post(f"/api/v1/students/{ids['student']}/facts/uoa", headers=h,
                     json={"value": ids["uoa1"], "effectiveDate": "2025-10-01"})
    assert r.status_code == 200, r.text
    assert (await c.get(f"/api/v1/students/{ids['student']}", headers=h)).json()["uoa"] == "1 Clinical Medicine"

    # The supervisor: UOA 1 from the start, moved to UOA 3 at the last minute (from 1 Jul 2026).
    for uoa, on in (("uoa1", "2025-08-01"), ("uoa3", "2026-07-01")):
        r = await c.post(f"/api/v1/persons/{ids['dr']}/uoa", headers=h,
                         json={"uoaId": ids[uoa], "effectiveDate": on, "reason": "REF mapping"})
        assert r.status_code == 200, r.text
    hist = (await c.get(f"/api/v1/persons/{ids['dr']}/uoa", headers=h)).json()
    assert [(p["uoa"], p["validFrom"], p["validTo"]) for p in hist["periods"]] == [
        ("1 Clinical Medicine", "2025-08-01", "2026-07-01"), ("3 Allied Health", "2026-07-01", None)]
    assert hist["current"] == "3 Allied Health"

    async with sm() as s:
        early = [r for r in await StatutoryEngine(s).build_records("2025/26", as_at=date(2026, 3, 1))
                 if r["student"]["ref"] == "PGR-UOA"][0]
        late = [r for r in await StatutoryEngine(s).build_records("2025/26")
                if r["student"]["ref"] == "PGR-UOA"][0]
    assert (early["student"]["uoa"], early["supervision"]["primaryUoa"]) == ("1", "1")
    assert (late["student"]["uoa"], late["supervision"]["primaryUoa"]) == ("1", "3")


async def test_supervisor_uoa_change_after_sign_off_is_listed(ctx, clock):
    c, h, ids, sm = ctx
    async with sm() as s:
        p = ReportProfile(code="HESA_STUDENT", name="HESA Student", academic_year="2025/26",
                          signed_off_at=datetime.now(timezone.utc) - timedelta(days=1))
        s.add(p); await s.commit()
        pid = p.id
    r = await c.post(f"/api/v1/persons/{ids['dr']}/uoa", headers=h,
                     json={"uoaId": ids["uoa3"], "effectiveDate": "2026-07-01"})
    assert r.status_code == 200, r.text
    async with sm() as s:
        out = await changes_since_signoff(s, pid)
    [student] = out["students"]
    assert student["studentRef"] == "PGR-UOA"
    assert [(x["fact"], x["value"]) for x in student["changes"] if x["fact"] == "supervisor_uoa"] == [
        ("supervisor_uoa", "primary supervisor: 3")]
