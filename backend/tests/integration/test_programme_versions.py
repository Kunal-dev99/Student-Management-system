"""Effective dating, Phase 8b — programme versions and cohort pinning (Demo 2 item 1.3, the CMA rule).

What must hold:
- a student is pinned to the programme version in force when they started on it
- a version students are on is locked: it may gain modules, but removing one, making a core
  module optional, or changing the rules (credits, duration, grading) is refused
- a new version from a date takes the changes; current students keep their version (and its core
  modules), while a cohort starting after the date is pinned to the new one
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




async def _versions(c, h, pid):
    r = await c.get(f"/api/v1/programmes/{pid}/versions", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["versions"]


async def test_student_is_pinned_to_the_version_in_force_when_they_started(ctx, clock):
    c, h, ids, _ = ctx
    [v1] = await _versions(c, h, ids["msc"])
    assert (v1["label"], v1["students"], v1["locked"], v1["validTo"]) == ("v1", 1, True, None)
    assert [(x["code"], x["isCore"]) for x in v1["structure"]] == [("ONC501", True)]
    r = await c.get(f"/api/v1/students/{ids['student']}", headers=h)
    assert r.json()["programmeVersion"] == "v1"


async def test_a_version_with_students_only_gains_modules(ctx, clock):
    c, h, ids, _ = ctx
    # Rules can't change under the cohort.
    r = await c.patch(f"/api/v1/programmes/{ids['msc']}", headers=h, json={"taughtTotalCredits": 120})
    assert r.status_code == 409 and "new programme version" in r.text
    # Adding a module is allowed and joins the version's structure.
    r = await c.post(f"/api/v1/programmes/{ids['msc']}/modules", headers=h, json={
        "code": "ONC502", "title": "Tumour Immunology", "credits": 15, "isCore": False})
    assert r.status_code == 201, r.text
    r = await c.post(f"/api/v1/programmes/{ids['msc']}/module-offerings", headers=h,
                     json={"moduleId": ids["foreign_module"]})
    assert r.status_code == 201, r.text
    [v1] = await _versions(c, h, ids["msc"])
    assert {x["code"] for x in v1["structure"]} == {"ONC501", "ONC502", "NEU501"}
    # Taking a module away, or making a core module optional, is refused.
    r = await c.delete(f"/api/v1/programmes/{ids['msc']}/module-offerings/{ids['foreign_module']}", headers=h)
    assert r.status_code == 409 and "remove NEU501" in r.text
    r = await c.patch(f"/api/v1/taught-modules/{ids['module']}", headers=h, json={"isCore": False})
    assert r.status_code == 409 and "make ONC501 optional" in r.text


async def test_new_version_for_the_next_cohort(ctx, clock):
    c, h, ids, _ = ctx
    r = await c.post(f"/api/v1/programmes/{ids['msc']}/versions", headers=h, json={
        "effectiveFrom": "2027-08-01", "taughtTotalCredits": 120,
        "note": "Shorter programme from 2027/28; ONC501 becomes optional"})
    assert r.status_code == 201, r.text
    v1, v2 = r.json()["versions"]
    assert (v1["validTo"], v2["validFrom"], v2["taughtTotalCredits"], v2["students"]) == (
        "2027-08-01", "2027-08-01", 120, 0)
    # v2 has no students yet, so its structure can change; v1 keeps ONC501 as core.
    r = await c.patch(f"/api/v1/taught-modules/{ids['module']}", headers=h, json={"isCore": False})
    assert r.status_code == 200, r.text
    v1, v2 = await _versions(c, h, ids["msc"])
    assert [x["isCore"] for x in v1["structure"]] == [True]
    assert [x["isCore"] for x in v2["structure"]] == [False]

    # A student starting after the date is pinned to v2, so ONC501 (now optional) isn't laid down.
    r = await c.post("/api/v1/students/enrol", headers=h, json={
        "person": {"givenName": "Ne", "familyName": "Xt"}, "programmeId": ids["msc"],
        "startDate": "2027-09-20"})
    assert r.status_code == 201, r.text
    new_id = r.json()["id"]
    assert (await c.get(f"/api/v1/students/{new_id}", headers=h)).json()["programmeVersion"] == "v2"
    assert (await c.get(f"/api/v1/students/{new_id}/module-enrolments", headers=h)).json() == []
    # The first cohort still has its core module.
    old = (await c.get(f"/api/v1/students/{ids['student']}/module-enrolments", headers=h)).json()
    assert [e["moduleCode"] for e in old] == ["ONC501"]
    assert (await c.get(f"/api/v1/students/{ids['student']}", headers=h)).json()["programmeVersion"] == "v1"


async def test_new_version_rules(ctx, clock):
    c, h, ids, _ = ctx
    url = f"/api/v1/programmes/{ids['msc']}/versions"
    r = await c.post(url, headers=h, json={"effectiveFrom": "2020-01-01", "note": "x"})
    assert r.status_code == 422 and "must start after" in r.text
    r = await c.post(url, headers=h, json={"effectiveFrom": "2027-08-01", "note": " "})
    assert r.status_code == 422 and "what changed" in r.text
