"""MT-5 — subdomain -> tenant resolution and host/token reconciliation."""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.database import engine
from app.core.dependencies import _reconcile_tenant
from app.core.errors import PermissionError as AppPermissionError
from app.core.tenant_resolver import subdomain_of


def test_subdomain_of_dev_only_localhost():
    # No base domain configured (dev): only <sub>.localhost resolves.
    assert subdomain_of("icr.localhost:3000") == "icr"
    assert subdomain_of("icr.localhost") == "icr"
    assert subdomain_of("localhost") is None
    assert subdomain_of("pgr.example.com") is None       # apex is not "pgr"
    assert subdomain_of("icr.pgr.example.com") is None   # needs base_domain to resolve
    assert subdomain_of("127.0.0.1") is None
    assert subdomain_of("test") is None
    assert subdomain_of("www.localhost") is None          # neutral label


def test_subdomain_of_prod_base_domain():
    base = "pgr.icr.ac.uk"
    assert subdomain_of("icr.pgr.icr.ac.uk", base) == "icr"
    assert subdomain_of("pgr.icr.ac.uk", base) is None    # apex
    assert subdomain_of("www.pgr.icr.ac.uk", base) is None
    assert subdomain_of("a.b.pgr.icr.ac.uk", base) == "a"
    assert subdomain_of("evil.com", base) is None         # outside our domain


def test_reconcile_tenant():
    a, b = uuid.uuid4(), uuid.uuid4()
    assert _reconcile_tenant(a, a) == a
    assert _reconcile_tenant(None, a) == a       # neutral host -> token tenant
    assert _reconcile_tenant(a, None) == a       # host tenant, no token tenant
    assert _reconcile_tenant(None, None) is None
    with pytest.raises(AppPermissionError):
        _reconcile_tenant(a, b)                  # token used on another tenant's subdomain


@pytest.mark.asyncio
async def test_cross_tenant_host_is_blocked():
    """A token for the default tenant cannot be used on another tenant's subdomain."""
    if engine.dialect.name != "postgresql":
        pytest.skip("needs Postgres (tenant row + resolver read the real DB)")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover
        pytest.skip("Postgres not reachable")

    from app.core import tenant_resolver
    from app.main import app

    tid = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM tenant WHERE subdomain = 'acmetest'"))
        await conn.execute(text(
            "INSERT INTO tenant(id, name, subdomain, activated_at, created_at, updated_at) "
            "VALUES (:id, 'Acme Test', 'acmetest', now(), now(), now())"
        ).bindparams(id=tid))
    tenant_resolver._reset_cache_for_tests()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/auth/login",
                             json={"email": "admin@example.com", "password": "admin123"})
            tok = r.json().get("accessToken") or r.json().get("access_token")
            auth = {"Authorization": f"Bearer {tok}"}
            ok = await c.get("/api/v1/programmes", headers={**auth, "host": "localhost"})
            blocked = await c.get("/api/v1/programmes", headers={**auth, "host": "acmetest.localhost"})
        assert ok.status_code == 200
        assert blocked.status_code == 403
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM tenant WHERE subdomain = 'acmetest'"))
        tenant_resolver._reset_cache_for_tests()
