"""F6 — assistant write-intent + notification hygiene (quiet hours + email bounce).

What must hold:
- proposing a Tier-3 blocked action is refused with the exact rule cited
- proposing a safe action creates a proposed intent
- executing an unsupported action moves the intent to failed with a reason
- executing 'meeting.log' moves it to executed
- a hard email bounce deactivates the user's email channel
- quiet-hours preference round-trips
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


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        # A user whose email matches a Person, so a bounce on that email deactivates their channel
        u = User(email="cc@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]
        person = Person(given_name="Cc", family_name="Person", email="cc@t.com")
        s.add(person); await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "cc@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_tier3_action_is_refused_at_propose(ctx):
    c, h = ctx
    r = await c.post("/api/v1/assistant/intents", headers=h, json={
        "action": "graduate_student",
        "scope": {"studentId": "x"},
        "preview": {"summary": "graduate"},
    })
    assert r.status_code == 422
    assert "tier-3" in r.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_propose_and_execute_meeting_log_flow(ctx):
    c, h = ctx
    r = await c.post("/api/v1/assistant/intents", headers=h, json={
        "action": "meeting.log",
        "scope": {"studentId": "some-uuid", "duration": 30},
        "preview": {"summary": "Log a 30-minute supervision meeting"},
    })
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    assert r.json()["state"] == "proposed"

    r = await c.post(f"/api/v1/assistant/intents/{iid}/execute", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "executed"
    assert body["outcome"]

    # A second execute is refused — intent is already executed
    r = await c.post(f"/api/v1/assistant/intents/{iid}/execute", headers=h)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_unsupported_action_moves_to_failed(ctx):
    c, h = ctx
    r = await c.post("/api/v1/assistant/intents", headers=h, json={
        "action": "does.not.exist",
        "scope": {}, "preview": {"summary": "nope"},
    })
    iid = r.json()["id"]
    r = await c.post(f"/api/v1/assistant/intents/{iid}/execute", headers=h)
    assert r.status_code == 200
    assert r.json()["state"] == "failed" and "no handler" in r.json()["outcome"].lower()


@pytest.mark.asyncio
async def test_cancel_a_proposed_intent(ctx):
    c, h = ctx
    r = await c.post("/api/v1/assistant/intents", headers=h, json={
        "action": "meeting.log", "scope": {}, "preview": {"summary": "cancel me"},
    })
    iid = r.json()["id"]
    r = await c.post(f"/api/v1/assistant/intents/{iid}/cancel", headers=h)
    assert r.status_code == 200 and r.json()["state"] == "cancelled"


@pytest.mark.asyncio
async def test_hard_bounce_deactivates_email_channel(ctx):
    c, h = ctx
    r = await c.post("/api/v1/notifications/webhooks/email/bounce", json={
        "email": "cc@t.com", "bounceType": "hard", "reason": "550 no such user",
    })
    assert r.status_code == 200
    assert r.json()["emailChannelDeactivated"] is True

    # Verify: my preferences show email off
    r = await c.get("/api/v1/notifications/preferences", headers=h)
    assert r.json()["emailEnabled"] is False


@pytest.mark.asyncio
async def test_soft_bounce_records_but_does_not_deactivate(ctx):
    c, h = ctx
    r = await c.post("/api/v1/notifications/webhooks/email/bounce", json={
        "email": "cc@t.com", "bounceType": "soft", "reason": "mailbox full",
    })
    assert r.status_code == 200
    assert r.json()["emailChannelDeactivated"] is False
    # Email still on
    assert (await c.get("/api/v1/notifications/preferences", headers=h)).json()["emailEnabled"] is True


@pytest.mark.asyncio
async def test_quiet_hours_round_trip(ctx):
    c, h = ctx
    r = await c.put("/api/v1/notifications/preferences", headers=h, json={
        "emailEnabled": True, "digest": True, "mutedEvents": [],
        "quietStart": 22 * 60, "quietEnd": 7 * 60,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["quietStart"] == 22 * 60 and body["quietEnd"] == 7 * 60 and body["digest"] is True
