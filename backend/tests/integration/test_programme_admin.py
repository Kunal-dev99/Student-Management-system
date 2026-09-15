"""ICR G3 (slice B) — programme + milestone-definition administration.

The register was read-only for programmes and their milestone templates (reachable only by
API/seed). This adds the admin CRUD the UI needs. What must hold:
- create / edit a programme (type, duration, supervision cadence); duplicate code is rejected
- edit and delete milestone definitions; a definition already scheduled for students can't be deleted
- a programme's duration drives a new student's expected end date at enrolment
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


async def _create_prog(c, h, code="PHD", **extra):
    body = {"name": "PhD", "code": code, "durationMonths": 48, **extra}
    return await c.post("/api/v1/programmes", headers=h, json=body)


@pytest.mark.asyncio
async def test_create_and_edit_programme(ctx):
    c, h = ctx
    r = await _create_prog(c, h, supervisionMeetingIntervalDays=90)
    assert r.status_code == 201, r.text
    prog = r.json()
    assert prog["durationMonths"] == 48 and prog["supervisionMeetingIntervalDays"] == 90

    upd = await c.patch(f"/api/v1/programmes/{prog['id']}", headers=h,
                        json={"name": "PhD (Science)", "durationMonths": 36})
    assert upd.status_code == 200, upd.text
    assert upd.json()["name"] == "PhD (Science)" and upd.json()["durationMonths"] == 36

    listed = (await c.get("/api/v1/programmes", headers=h)).json()
    assert any(p["code"] == "PHD" and p["name"] == "PhD (Science)" for p in listed)


@pytest.mark.asyncio
async def test_duplicate_code_rejected(ctx):
    c, h = ctx
    assert (await _create_prog(c, h, code="DUP")).status_code == 201
    assert (await _create_prog(c, h, code="DUP")).status_code == 409


@pytest.mark.asyncio
async def test_edit_and_delete_milestone_definition(ctx):
    c, h = ctx
    prog = (await _create_prog(c, h, code="MSTONE")).json()
    pid = prog["id"]
    defn = (await c.post(f"/api/v1/programmes/{pid}/milestone-definitions", headers=h,
                         json={"name": "Induction", "dueOffsetDays": 30})).json()

    edited = await c.patch(f"/api/v1/programmes/{pid}/milestone-definitions/{defn['id']}",
                           headers=h, json={"dueOffsetDays": 45})
    assert edited.status_code == 200, edited.text
    assert edited.json()["dueOffsetDays"] == 45

    deleted = await c.delete(f"/api/v1/programmes/{pid}/milestone-definitions/{defn['id']}", headers=h)
    assert deleted.status_code == 204, deleted.text
    remaining = (await c.get(f"/api/v1/programmes/{pid}/milestone-definitions", headers=h)).json()
    assert remaining == []


@pytest.mark.asyncio
async def test_cannot_delete_a_definition_in_use(ctx):
    c, h = ctx
    prog = (await _create_prog(c, h, code="INUSE")).json()
    pid = prog["id"]
    defn = (await c.post(f"/api/v1/programmes/{pid}/milestone-definitions", headers=h,
                         json={"name": "Confirmation", "dueOffsetDays": 270})).json()
    # Enrol a student -> the definition is now instantiated as a milestone.
    await c.post("/api/v1/students/enrol", headers=h, json={
        "person": {"givenName": "Sam", "familyName": "Rao"}, "programmeId": pid,
    })
    blocked = await c.delete(f"/api/v1/programmes/{pid}/milestone-definitions/{defn['id']}", headers=h)
    assert blocked.status_code == 409, blocked.text


@pytest.mark.asyncio
async def test_programme_duration_sets_expected_end_date(ctx):
    c, h = ctx
    prog = (await _create_prog(c, h, code="DUR", durationMonths=48)).json()
    enrolled = (await c.post("/api/v1/students/enrol", headers=h, json={
        "person": {"givenName": "Mia", "familyName": "Chen"},
        "programmeId": prog["id"], "startDate": "2026-01-01", "studyMode": "full_time",
    })).json()
    assert enrolled["expectedEndDate"] == "2030-01-01"  # +48 months
    assert enrolled["originalExpectedEndDate"] == "2030-01-01"
