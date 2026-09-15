"""ICR G2 (slice C) — the recruitment.enabled feature flag surfaced on /me.

The client hides the recruitment funnel (Research demand / Opportunities / Recruitment /
Admissions) when an institution recruits in a separate system. The nav needs the flag for every
user, so it rides on /me. What must hold:
- recruitment is ON by default (no override) -> features.recruitment is True
- turning the institution setting off flips the flag the client reads
The API remains the enforcement layer; this flag only shapes the UI.
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


@pytest.mark.asyncio
async def test_recruitment_feature_defaults_on(ctx):
    c, h = ctx
    me = (await c.get("/api/v1/me", headers=h)).json()
    assert me["features"]["recruitment"] is True


@pytest.mark.asyncio
async def test_turning_recruitment_off_flips_the_flag(ctx):
    c, h = ctx
    r = await c.put("/api/v1/settings/institution/recruitment.enabled", headers=h,
                    json={"value": False})
    assert r.status_code == 200, r.text
    me = (await c.get("/api/v1/me", headers=h)).json()
    assert me["features"]["recruitment"] is False
