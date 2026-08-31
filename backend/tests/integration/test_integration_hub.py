"""Integration hub: outbox dispatcher + signed idempotent webhooks (BE-2.4, arch §10)."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.modules.identity.models import Permission, Role, User
from app.modules.workflow.models import OutboxEvent


def _sign(raw: bytes) -> str:
    return hmac.new(get_settings().app_secret_key.encode(), raw, hashlib.sha256).hexdigest()


@pytest_asyncio.fixture
async def client():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perm = Permission(code="admin.configure"); s.add(perm); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = [perm]
        user = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]
        now = datetime.now(timezone.utc)
        s.add_all([
            OutboxEvent(aggregate_type="funding_arrangement", aggregate_id=uuid.uuid4(),
                        event_type="funding.changed", payload={"x": 1}, created_at=now),
            OutboxEvent(aggregate_type="milestone", aggregate_id=uuid.uuid4(),
                        event_type="milestone.submitted", payload={}, created_at=now),
        ])
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        c.headers.update({"Authorization": f"Bearer {r.json()['accessToken']}"})
        yield c
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_dispatch_routes_and_is_idempotent(client):
    r = await client.post("/api/v1/integration/dispatch")
    assert r.status_code == 200
    # 2 outbox events dispatched; 1 outbound call (funding.changed -> finance). milestone -> internal.
    body = r.json()
    assert body["dispatched"] == 2 and body["outboundCalls"] == 1
    assert body["failed"] == 0 and body["deadLettered"] == 0  # no partner URLs configured

    overview = (await client.get("/api/v1/integration/logs")).json()
    assert overview["pending"] == 0
    systems = sorted(l["system"] for l in overview["logs"])
    assert "finance" in systems and "internal" in systems

    # Re-dispatch does nothing (idempotent — events already marked dispatched).
    assert (await client.post("/api/v1/integration/dispatch")).json()["dispatched"] == 0


@pytest.mark.asyncio
async def test_signed_webhook_idempotent(client):
    # Use an event type Finance has no handler for — this test is about idempotency of the
    # inbound recorder, not the W3 payment handler (which owns payment.* on its own).
    body = json.dumps({"sourceId": "fin-123", "eventType": "invoice.raised", "payload": {"amount": 19000}}).encode()
    sig = _sign(body)

    r = await client.post("/api/v1/integration/webhooks/finance", content=body, headers={"X-Signature": sig, "Content-Type": "application/json"})
    # Phase 6: an inbound message we have no handler for is still recorded, but reported as
    # `logged_only` rather than `processed` — recorded is not the same as applied.
    assert r.status_code == 200 and r.json()["status"] == "logged_only"

    # Same source id again -> duplicate, not processed twice.
    r = await client.post("/api/v1/integration/webhooks/finance", content=body, headers={"X-Signature": sig, "Content-Type": "application/json"})
    assert r.json()["status"] == "duplicate"


@pytest.mark.asyncio
async def test_webhook_bad_signature_rejected(client):
    body = json.dumps({"sourceId": "x", "eventType": "e"}).encode()
    r = await client.post("/api/v1/integration/webhooks/finance", content=body, headers={"X-Signature": "deadbeef"})
    assert r.status_code == 401
