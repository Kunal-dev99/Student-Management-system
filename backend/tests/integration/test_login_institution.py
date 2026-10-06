"""Signing in with an institution picked on the sign-in page.

The account decides which institution a session belongs to; when the sign-in page names an
institution, an account from a different one is refused rather than quietly signed in to its own.
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.identity.models import User
from app.modules.tenant.models import Tenant

ICR = uuid.UUID("00000000-0000-0000-0000-000000000001")
OXB = uuid.UUID("00000000-0000-0000-0000-0000000000b2")


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        s.add_all([Tenant(id=ICR, name="Institute of Cancer Research", subdomain="default"),
                   Tenant(id=OXB, name="Oxbridge University", subdomain="oxbridge")])
        await s.flush()
        s.add(User(email="approver@oxbridge.demo", password_hash=hash_password("pw"), is_active=True, tenant_id=OXB))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, sm
    app.dependency_overrides.clear()
    await eng.dispose()


async def _login(c, password="pw", tenant=None):
    body = {"email": "approver@oxbridge.demo", "password": password}
    if tenant:
        body["tenantId"] = str(tenant)
    return await c.post("/api/v1/auth/login", json=body)


async def test_own_institution_signs_in(ctx):
    c, _ = ctx
    r = await _login(c, tenant=OXB)
    assert r.status_code == 200 and r.json()["accessToken"]


async def test_another_institution_is_refused_without_a_session(ctx):
    c, sm = ctx
    r = await _login(c, tenant=ICR)
    assert r.status_code == 401
    msg = r.json()["error"]["message"]
    assert "isn't registered with Institute of Cancer Research" in msg
    assert "accessToken" not in r.json()
    # Correct credentials, wrong picker: not a failed attempt, so nobody gets locked out by it.
    async with sm() as s:
        user = (await s.execute(select(User).where(User.email == "approver@oxbridge.demo"))).scalar_one()
    assert (user.failed_login_count or 0) == 0


async def test_wrong_password_stays_generic_whatever_is_picked(ctx):
    c, _ = ctx
    r = await _login(c, password="nope", tenant=ICR)
    assert r.status_code == 401 and r.json()["error"]["message"] == "Invalid email or password"


async def test_no_institution_given_behaves_as_before(ctx):
    c, _ = ctx
    assert (await _login(c)).status_code == 200
