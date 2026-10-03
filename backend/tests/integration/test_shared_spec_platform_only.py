"""The statutory specification is shared by every institution, so only the platform team (holders
of the vendor-only `platform.configure`) can change it: ingest, import, accept or reject an
advisory, or suppress a rule for the whole pack. An Institution Administrator ("*", which never
includes vendor-only permissions) can still read it and suppress rules for its own profiles."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.identity.constants import EXCLUSIVE_PERMISSIONS, PERMISSIONS
from app.modules.identity.models import Permission, Role, User


@pytest_asyncio.fixture
async def institution_admin():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = [Permission(code=c) for c in PERMISSIONS if c not in EXCLUSIVE_PERMISSIONS]
        s.add_all(perms); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = perms
        u = User(email="admin@inst.example.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "admin@inst.example.com", "password": "pw"})
        yield c, {"Authorization": f"Bearer {r.json()['accessToken']}"}
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_institution_admin_cannot_change_the_shared_specification(institution_admin):
    c, h = institution_admin
    some = uuid.uuid4()
    refused = [
        ("/api/v1/report-advisories/ingest", {"title": "x", "rawText": "YEAR: 2027/28"}),
        ("/api/v1/report-advisories/import-spec", {}),
        (f"/api/v1/report-advisories/{some}/accept", {}),
        (f"/api/v1/report-advisories/{some}/reject", {}),
        (f"/api/v1/report-profiles/{some}/suppress-rule", {"ruleKey": "r", "reason": "x", "scope": "pack"}),
        (f"/api/v1/report-profiles/{some}/remove-suppression", {"ruleKey": "r", "scope": "pack"}),
    ]
    for url, body in refused:
        r = await c.post(url, headers=h, json=body)
        assert r.status_code == 403, (url, r.status_code, r.text)


@pytest.mark.asyncio
async def test_institution_admin_can_still_read_it_and_suppress_for_its_own_profile(institution_admin):
    c, h = institution_admin
    assert (await c.get("/api/v1/report-advisories", headers=h)).status_code == 200
    # Profile scope is the institution's own business: not refused (404 here, as the id is made up).
    r = await c.post(f"/api/v1/report-profiles/{uuid.uuid4()}/suppress-rule", headers=h,
                     json={"ruleKey": "r", "reason": "x", "scope": "profile"})
    assert r.status_code != 403, r.text
