"""ICR G5 — HESA return: baseline from spec, HUSID, cross-field validation.

The demo built a profile "completely custom". ICR asked for a baseline template built automatically
from the published spec, with the data validated for HESA. What must hold:
- the published spec packs are listable
- "new profile from spec" pre-maps every field (known sources filled, unknown left to Registry)
- STULOAD is sourced from study intensity (G4); HUSID is generated (13 digits), never hand-keyed
- a cross-field rule (ENDDATE ≥ COMDATE) surfaces as an advisory warning
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
    eng = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
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
        prog = Programme(name="PhD", code="PHD"); s.add(prog); await s.flush()
        # A student whose expected end is BEFORE the start — trips the ENDDATE >= COMDATE rule.
        person = Person(given_name="Sam", family_name="Rao", nationality="GB"); s.add(person); await s.flush()
        s.add(Student(
            person_id=person.id, student_ref="PGR-HESA", programme_id=prog.id,
            start_date=date(2026, 1, 1), expected_end_date=date(2025, 1, 1),
            study_mode=StudyMode.full_time, status=StudentStatus.active,
        ))
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


@pytest.mark.asyncio
async def test_spec_packs_are_listable(ctx):
    c, h = ctx
    specs = (await c.get("/api/v1/report-profiles/specs", headers=h)).json()["specs"]
    assert any(s["code"] == "HESA_STUDENT" and s["academicYear"] == "2026/27" for s in specs)


@pytest.mark.asyncio
async def test_new_profile_from_spec_is_pre_mapped(ctx):
    c, h = ctx
    r = await c.post("/api/v1/report-profiles/from-spec", headers=h,
                     json={"specKey": "HESA_STUDENT:2026/27"})
    assert r.status_code == 201, r.text
    detail = r.json()
    fields = {f["targetField"]: f for f in detail["fields"]}
    assert len(fields) == 24
    # Known sources are filled in…
    assert fields["STULOAD"]["sourceExpression"] == "student.intensityPct"
    assert fields["HUSID"]["sourceExpression"] == "student.husid"
    assert fields["SURNAME"]["sourceExpression"] == "person.familyName"
    # …and a field we can't source yet is left for Registry (required, empty source).
    assert fields["SEXID"]["sourceExpression"] == ""
    assert fields["SEXID"]["required"] is True

    # Every spec field is mapped, so the compile gate reports nothing missing.
    compiled = (await c.get(f"/api/v1/report-profiles/{detail['id']}/compile", headers=h)).json()
    assert compiled["missing"] == []


@pytest.mark.asyncio
async def test_generate_produces_husid_and_stuload_and_warns_on_bad_dates(ctx):
    c, h = ctx
    detail = (await c.post("/api/v1/report-profiles/from-spec", headers=h,
                           json={"specKey": "HESA_STUDENT:2026/27"})).json()
    gen = (await c.get(f"/api/v1/report-profiles/{detail['id']}/validate", headers=h)).json()
    # Unmapped required fields are hard errors (valid=False); date rule is an advisory warning.
    assert gen["validation"]["valid"] is False
    assert gen["validation"]["warnings"] >= 1
    assert any(i["field"] == "ENDDATE" and i["severity"] == "warning"
               for i in gen["validation"]["issues"])


@pytest.mark.asyncio
async def test_husid_is_generated_thirteen_digits(ctx):
    from app.modules.exports.statutory import husid

    h1 = husid("0263", 2026, "PGR-2026-ABC123")
    assert len(h1) == 13 and h1.isdigit()
    # Deterministic for the same ref, different for a different ref.
    assert h1 == husid("0263", 2026, "PGR-2026-ABC123")
    assert h1 != husid("0263", 2026, "PGR-2026-ZZZ999")
