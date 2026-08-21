"""Phase 0 smoke tests (BE-0.1, BE-0.4, BE-0.8)."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_live(client):
    r = await client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "live"}


@pytest.mark.asyncio
async def test_openapi_published(client):
    r = await client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    assert r.json()["openapi"].startswith("3.")


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    # /me is now guarded (identity module, BE-1.0a). Unauthenticated -> standard envelope.
    r = await client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"
