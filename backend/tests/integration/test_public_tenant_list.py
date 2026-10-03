"""The login page's public institution list must not publish every customer in production.

With TENANT_BASE_DOMAIN set it returns only the institution the address names (the bare base
domain is the default deployment); without it (dev, demos) it lists every active institution."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core import tenant_resolver
from app.core.config import get_settings
from app.core.tenant_context import DEFAULT_TENANT_ID
from app.db.base import Base
from app.db.session import get_read_session
from app.main import app
from app.modules.tenant.models import Tenant

ICR = uuid.UUID("00000000-0000-0000-0000-0000000000c1")


@pytest_asyncio.fixture
async def client():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with sm() as s:
        existing = await s.get(Tenant, DEFAULT_TENANT_ID)
        if existing is None:
            s.add(Tenant(id=DEFAULT_TENANT_ID, name="Default", subdomain="default", activated_at=now))
        s.add(Tenant(id=ICR, name="ICR", subdomain="icr", activated_at=now))
        s.add(Tenant(name="Oxbridge", subdomain="oxbridge", activated_at=now))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await eng.dispose()


async def _subdomains(c) -> set[str]:
    r = await c.get("/api/v1/tenants")
    assert r.status_code == 200, r.text
    return {t["subdomain"] for t in r.json()}


@pytest.mark.asyncio
async def test_dev_lists_every_active_institution(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "tenant_base_domain", None)
    monkeypatch.setattr(get_settings(), "app_env", "dev")
    assert {"icr", "oxbridge"} <= await _subdomains(client)


@pytest.mark.asyncio
async def test_production_lists_only_the_institution_the_address_names(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "tenant_base_domain", "pgr.fusionpractices.com")

    async def on_icr(_request):
        return ICR

    async def on_apex(_request):
        return None

    monkeypatch.setattr(tenant_resolver, "tenant_for_request", on_icr)
    assert await _subdomains(client) == {"icr"}
    monkeypatch.setattr(tenant_resolver, "tenant_for_request", on_apex)
    assert await _subdomains(client) == {"default"}


@pytest.mark.asyncio
async def test_single_address_production_lists_nothing(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "tenant_base_domain", None)
    monkeypatch.setattr(get_settings(), "app_env", "production")
    assert await _subdomains(client) == set()
