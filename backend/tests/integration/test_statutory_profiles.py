"""Phase 6.6 — statutory reporting as a configurable layer (CIO vision GAP-05).

HESA is an *external specification*, not core domain logic. What must hold:
- a return is produced entirely from configuration — no Python per return
- validation reports errors **per student per field**, before the file goes anywhere
- profiles are versioned by academic year, so a prior year can be reproduced
- an unknown transform is rejected at configuration time, not at generation time
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
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        user = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]

        prog = Programme(name="PhD CS", code="PHD-CS"); s.add(prog); await s.flush()

        # One complete student and one missing nationality, to exercise validation.
        full = Person(given_name="Ada", family_name="Complete", nationality="British")
        partial = Person(given_name="Bo", family_name="Missing")     # no nationality
        s.add_all([full, partial]); await s.flush()
        for person, ref in ((full, "PGR-A"), (partial, "PGR-B")):
            s.add(Student(person_id=person.id, student_ref=ref, programme_id=prog.id,
                          start_date=date(2026, 10, 1), expected_end_date=date(2029, 9, 30),
                          study_mode=StudyMode.full_time, status=StudentStatus.active))
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
        yield c, h
    app.dependency_overrides.clear()
    await eng.dispose()


async def _profile(c, h, year="2026/27"):
    return (await c.post("/api/v1/report-profiles", headers=h, json={
        "code": "HESA_STUDENT", "name": "HESA Student Return", "academicYear": year})).json()


async def _field(c, h, pid, target, source, **kw):
    return await c.post(f"/api/v1/report-profiles/{pid}/fields", headers=h,
                        json={"targetField": target, "sourceExpression": source, **kw})


@pytest.mark.asyncio
async def test_a_return_is_produced_entirely_from_configuration(ctx):
    c, h = ctx
    p = await _profile(c, h)
    await _field(c, h, p["id"], "HUSID", "student.ref", required=True)
    await _field(c, h, p["id"], "SURNAME", "person.familyName", transform="upper", required=True)
    await _field(c, h, p["id"], "COMDATE", "student.startDate", transform="date_compact")

    result = (await c.post(f"/api/v1/report-profiles/{p['id']}/generate", headers=h, json={})).json()
    assert result["job"]["rowCount"] == 2
    assert result["validation"]["valid"] is True

    csv_text = (await c.get(f"/api/v1/exports/{result['job']['id']}/download", headers=h)).text
    lines = csv_text.strip().splitlines()
    assert lines[0] == "HUSID,SURNAME,COMDATE"          # header comes from the mapping
    assert "COMPLETE" in lines[1]                        # transform applied
    assert "20261001" in lines[1]                        # date_compact applied


@pytest.mark.asyncio
async def test_validation_reports_the_offending_student_and_field(ctx):
    c, h = ctx
    p = await _profile(c, h)
    await _field(c, h, p["id"], "HUSID", "student.ref", required=True)
    await _field(c, h, p["id"], "NATION", "person.nationality", required=True)   # Bo has none

    report = (await c.get(f"/api/v1/report-profiles/{p['id']}/validate", headers=h)).json()
    assert report["validation"]["valid"] is False
    issue = next(i for i in report["validation"]["issues"] if i["field"] == "NATION")
    assert issue["studentRef"] == "PGR-B"
    assert issue["severity"] == "error"
    assert "required" in issue["message"].lower()
    assert issue["sourceExpression"] == "person.nationality"   # points at the mapping to fix


@pytest.mark.asyncio
async def test_allowed_values_are_enforced(ctx):
    c, h = ctx
    p = await _profile(c, h)
    await _field(c, h, p["id"], "STULOAD", "student.mode", allowed_values=["FT", "PT"])
    report = (await c.get(f"/api/v1/report-profiles/{p['id']}/validate", headers=h)).json()
    issue = report["validation"]["issues"][0]
    assert "not an accepted value" in issue["message"]
    assert issue["allowed"] == ["FT", "PT"]


@pytest.mark.asyncio
async def test_default_value_fills_a_blank(ctx):
    c, h = ctx
    p = await _profile(c, h)
    await _field(c, h, p["id"], "HUSID", "student.ref", required=True)
    await _field(c, h, p["id"], "NATION", "person.nationality", required=True,
                 default_value="UNKNOWN")
    report = (await c.get(f"/api/v1/report-profiles/{p['id']}/validate", headers=h)).json()
    assert report["validation"]["valid"] is True     # the default satisfied the requirement


@pytest.mark.asyncio
async def test_unknown_source_path_is_blank_not_a_crash(ctx):
    """Configuration referencing a field that no longer exists must degrade, not explode."""
    c, h = ctx
    p = await _profile(c, h)
    await _field(c, h, p["id"], "HUSID", "student.ref")
    await _field(c, h, p["id"], "GHOST", "student.doesNotExist.at.all")
    result = (await c.post(f"/api/v1/report-profiles/{p['id']}/generate", headers=h, json={})).json()
    assert result["job"]["rowCount"] == 2


@pytest.mark.asyncio
async def test_unknown_transform_is_rejected_at_configuration_time(ctx):
    c, h = ctx
    p = await _profile(c, h)
    r = await _field(c, h, p["id"], "X", "student.ref", transform="explode")
    assert r.status_code == 422
    assert "unknown transform" in r.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_duplicate_target_field_is_refused(ctx):
    c, h = ctx
    p = await _profile(c, h)
    await _field(c, h, p["id"], "HUSID", "student.ref")
    assert (await _field(c, h, p["id"], "HUSID", "person.email")).status_code == 409


@pytest.mark.asyncio
async def test_profile_is_versioned_by_year_and_can_be_cloned(ctx):
    c, h = ctx
    p = await _profile(c, h, "2026/27")
    await _field(c, h, p["id"], "HUSID", "student.ref", required=True)
    await _field(c, h, p["id"], "SURNAME", "person.familyName", transform="upper")

    # Same code+year+version cannot be created twice.
    assert (await c.post("/api/v1/report-profiles", headers=h, json={
        "code": "HESA_STUDENT", "name": "dup", "academicYear": "2026/27"})).status_code == 409

    clone = (await c.post(f"/api/v1/report-profiles/{p['id']}/clone", headers=h,
                          json={"academicYear": "2027/28"})).json()
    assert clone["academicYear"] == "2027/28"
    detail = (await c.get(f"/api/v1/report-profiles/{clone['id']}", headers=h)).json()
    assert [f["targetField"] for f in detail["fields"]] == ["HUSID", "SURNAME"]  # carried forward

    # The prior year is untouched, so it can still be regenerated as it was.
    old = (await c.get(f"/api/v1/report-profiles/{p['id']}", headers=h)).json()
    assert old["academicYear"] == "2026/27" and len(old["fields"]) == 2


@pytest.mark.asyncio
async def test_profile_without_fields_cannot_generate(ctx):
    c, h = ctx
    p = await _profile(c, h)
    r = await c.post(f"/api/v1/report-profiles/{p['id']}/generate", headers=h, json={})
    assert r.status_code == 422
    assert "no field mappings" in r.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_transforms_are_discoverable(ctx):
    c, h = ctx
    body = (await c.get("/api/v1/report-profiles/transforms", headers=h)).json()
    assert "upper" in body["transforms"] and "date_compact" in body["transforms"]
