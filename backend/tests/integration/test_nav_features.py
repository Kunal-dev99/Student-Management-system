"""Configurable navigation — the runtime park mechanism for the sidebar.

An admin toggles a sidebar feature off; it disappears from /me's feature map (as a disabled entry)
and the overview reflects it, while core screens can never be disabled. Turning it back on clears
the disabled entry. Enforcement of the route itself stays server-side per endpoint; this only
drives what the nav shows.
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
        u = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]
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
async def test_defaults_all_on_and_me_has_no_disabled_nav(ctx):
    c, h = ctx
    ov = (await c.get("/api/v1/settings/nav-features", headers=h)).json()
    items = [it for g in ov["groups"] for it in g["items"]]
    assert all(it["enabled"] for it in items)
    assert {"Main", "Administration", "Advanced"} <= {g["group"] for g in ov["groups"]}
    me = (await c.get("/api/v1/me", headers=h)).json()
    assert not any(k.startswith("nav:") for k in me["features"])  # nothing disabled yet


@pytest.mark.asyncio
async def test_disable_hides_it_from_me_then_reenable_clears_it(ctx):
    c, h = ctx
    off = await c.put("/api/v1/settings/nav-features", headers=h,
                      json={"route": "/pattern-lab", "enabled": False})
    assert off.status_code == 200, off.text

    me = (await c.get("/api/v1/me", headers=h)).json()
    assert me["features"].get("nav:/pattern-lab") is False
    # Other routes stay absent (client treats absent as on).
    assert "nav:/statutory" not in me["features"]

    ov = (await c.get("/api/v1/settings/nav-features", headers=h)).json()
    pattern = next(it for g in ov["groups"] for it in g["items"] if it["route"] == "/pattern-lab")
    assert pattern["enabled"] is False

    on = await c.put("/api/v1/settings/nav-features", headers=h,
                     json={"route": "/pattern-lab", "enabled": True})
    assert on.status_code == 200
    me = (await c.get("/api/v1/me", headers=h)).json()
    assert "nav:/pattern-lab" not in me["features"]


@pytest.mark.asyncio
async def test_core_screens_cannot_be_disabled(ctx):
    c, h = ctx
    for route in ("/settings", "/dashboard"):
        r = await c.put("/api/v1/settings/nav-features", headers=h,
                        json={"route": route, "enabled": False})
        assert r.status_code == 400, f"{route}: {r.text}"


@pytest.mark.asyncio
async def test_unknown_route_is_404(ctx):
    c, h = ctx
    r = await c.put("/api/v1/settings/nav-features", headers=h,
                    json={"route": "/nope", "enabled": False})
    assert r.status_code == 404
