"""Effective dating, Phase 8a — module versions and yearly runs (Demo 2 item 1.3, the CMA rule).

What must hold:
- a new module gets version 1 from the start of the current academic year
- an enrolment belongs to the run of the version in force at its year's start
- a version students are enrolled on can't be edited (CMA); a version nobody is on can be
- a new version from a date closes the old one; students already on the old version keep its
  credits, while later cohorts (and a student repeating the module) get the new version
- a new version must start after the current one and needs a note
- the module row caches today's version; the daily refresh moves it on the effective date
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
from app.modules.student_record import fact_history
from app.modules.student_record.constants import ProgrammeType
from app.modules.student_record.models import Programme
from app.modules.taught.catalogue import ModuleCatalogueService
from app.modules.taught.models import TaughtModule

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



async def _catalogue(c, h, mid):
    r = await c.get(f"/api/v1/taught-modules/{mid}/catalogue", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def _enrolments(c, h, sid):
    r = await c.get(f"/api/v1/students/{sid}/module-enrolments", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def test_new_module_gets_version_one_and_enrolment_joins_its_run(ctx, clock):
    c, h, ids, _ = ctx
    cat = await _catalogue(c, h, ids["module"])
    [v1] = cat["versions"]
    assert (v1["label"], v1["credits"], v1["validTo"]) == ("v1", 30, None)
    assert v1["validFrom"].endswith("-08-01") and v1["locked"] is True   # the student is on it
    assert [(r["academicYear"], r["version"], r["enrolments"]) for r in cat["runs"]] == [("2026/27", "v1", 1)]
    [e] = await _enrolments(c, h, ids["student"])
    assert (e["moduleVersion"], e["credits"]) == ("v1", 30)


async def test_a_version_with_students_cant_be_edited(ctx, clock):
    c, h, ids, _ = ctx
    r = await c.patch(f"/api/v1/taught-modules/{ids['module']}", headers=h, json={"credits": 15})
    assert r.status_code == 409 and "new version" in r.text
    # Fields that aren't what the module teaches (e.g. its code) can still change.
    r = await c.patch(f"/api/v1/taught-modules/{ids['module']}", headers=h, json={"code": "ONC501A"})
    assert r.status_code == 200, r.text
    # A module nobody is enrolled on can be edited in place.
    r = await c.patch(f"/api/v1/taught-modules/{ids['foreign_module']}", headers=h, json={"credits": 15})
    assert r.status_code == 200 and r.json()["credits"] == 15
    assert (await _catalogue(c, h, ids["foreign_module"]))["versions"][0]["credits"] == 15


async def test_new_version_keeps_enrolled_students_on_theirs(ctx, clock):
    c, h, ids, sm = ctx
    r = await c.post(f"/api/v1/taught-modules/{ids['module']}/versions", headers=h, json={
        "effectiveFrom": "2027-08-01", "credits": 15, "title": "Cancer Biology (revised)",
        "note": "Split into two 15-credit modules from 2027/28"})
    assert r.status_code == 201, r.text
    assert r.json()["label"] == "v2"
    cat = await _catalogue(c, h, ids["module"])
    assert [(v["label"], v["validFrom"], v["validTo"]) for v in cat["versions"]] == [
        ("v1", cat["versions"][0]["validFrom"], "2027-08-01"), ("v2", "2027-08-01", None)]

    # The 2026/27 student keeps v1's 30 credits; repeating the module in 2027/28 is a new
    # enrolment on v2.
    r = await c.post(f"/api/v1/students/{ids['student']}/module-enrolments", headers=h,
                     json={"moduleId": ids["module"], "academicYear": "2027/28"})
    assert r.status_code == 201, r.text
    got = sorted((e["academicYear"], e["moduleVersion"], e["credits"], e["moduleTitle"])
                 for e in await _enrolments(c, h, ids["student"]))
    assert got == [("2026/27", "v1", 30, "Cancer Biology"),
                   ("2027/28", "v2", 15, "Cancer Biology (revised)")]

    # Today (2027-03-01) the module still shows v1; on 1 Aug the daily refresh moves it to v2.
    async with sm() as s:
        m = await s.get(TaughtModule, __import__("uuid").UUID(ids["module"]))
        assert m.credits == 30
        clock["today"] = date(2027, 8, 1)
        assert await ModuleCatalogueService(s).refresh_due() >= 1
        assert (m.credits, m.title) == (15, "Cancer Biology (revised)")


async def test_new_version_rules(ctx, clock):
    c, h, ids, _ = ctx
    url = f"/api/v1/taught-modules/{ids['module']}/versions"
    r = await c.post(url, headers=h, json={"effectiveFrom": "2020-01-01", "credits": 15, "note": "x"})
    assert r.status_code == 422 and "must start after" in r.text
    r = await c.post(url, headers=h, json={"effectiveFrom": "2027-08-01", "credits": 15, "note": " "})
    assert r.status_code == 422 and "what changed" in r.text
    r = await c.post(url, headers=h, json={"effectiveFrom": "2027-08-01", "note": "nothing"})
    assert r.status_code == 422 and "at least one change" in r.text


async def test_module_fte_is_set_or_derived_per_version(ctx, clock):
    """Phase 8c — module FTE: derived from credits ÷ programme credits (30 / 180 = 16.67%) until a
    version sets its own; a new version can change it without touching the enrolled cohort's."""
    c, h, ids, _ = ctx
    [v1] = (await _catalogue(c, h, ids["module"]))["versions"]
    assert (v1["ftePct"], v1["fteDerived"]) == (16.67, True)
    r = await c.post(f"/api/v1/taught-modules/{ids['module']}/versions", headers=h, json={
        "effectiveFrom": "2027-08-01", "ftePct": 25, "note": "Heavier lab component from 2027/28"})
    assert r.status_code == 201, r.text
    assert (r.json()["ftePct"], r.json()["fteDerived"]) == (25.0, False)
    v1, v2 = (await _catalogue(c, h, ids["module"]))["versions"]
    assert v1["ftePct"] == 16.67 and v2["ftePct"] == 25.0
    r = await c.post(f"/api/v1/taught-modules/{ids['module']}/versions", headers=h, json={
        "effectiveFrom": "2028-08-01", "ftePct": 150, "note": "too much"})
    assert r.status_code == 422
