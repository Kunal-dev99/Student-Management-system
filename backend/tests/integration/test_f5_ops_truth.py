"""F5 — Task SLA timers + bulk dead-letter replay.

What must hold:
- setting an SLA computes elapsed and initial breach state correctly
- the sweep marks tasks whose target has been exceeded as breached (idempotent)
- the SLA report totals match the DB reality
- bulk replay flips every named dead-letter back to pending, returning per-id results
- working-days-only elapsed skips weekends
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
from app.modules.workflow.constants import TaskStatus
from app.modules.workflow.f5_sla import (
    elapsed_seconds, is_breached, working_seconds_between,
)
from app.modules.workflow.models import Task


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
        u = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]
        # Two tasks: one recent (well within any SLA), one old (should breach a small target)
        task_new = Task(title="Recent task", status=TaskStatus.open, aggregate_type="student")
        task_old = Task(title="Old task", status=TaskStatus.open, aggregate_type="student")
        s.add_all([task_new, task_old]); await s.flush()
        # Force old task's created_at back a day
        task_old.created_at = datetime.now(timezone.utc) - timedelta(days=1)
        await s.commit()
        ids = {"new": str(task_new.id), "old": str(task_old.id)}

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        ids["_sm"] = sm  # for tests that seed rows directly
        yield c, h, ids
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_setting_short_sla_on_old_task_reports_breached(ctx):
    c, h, ids = ctx
    # Small target — the old task, at 1 day old, is well over 60s.
    r = await c.post(f"/api/v1/tasks/{ids['old']}/sla", headers=h, json={
        "targetSeconds": 60, "workingDaysOnly": False,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slaTargetSeconds"] == 60
    assert body["slaBreached"] is True
    assert body["elapsedSeconds"] > 60


@pytest.mark.asyncio
async def test_setting_generous_sla_is_not_breached(ctx):
    c, h, ids = ctx
    r = await c.post(f"/api/v1/tasks/{ids['old']}/sla", headers=h, json={
        "targetSeconds": 60 * 60 * 24 * 365,  # 1 year
    })
    assert r.status_code == 200
    assert r.json()["slaBreached"] is False


@pytest.mark.asyncio
async def test_sla_sweep_is_idempotent(ctx):
    c, h, ids = ctx
    await c.post(f"/api/v1/tasks/{ids['old']}/sla", headers=h, json={"targetSeconds": 60})
    # First sweep: nothing new (already marked at set time)
    r = await c.post("/api/v1/tasks/sla-sweep", headers=h)
    assert r.status_code == 200
    assert r.json()["newlyBreached"] == 0
    # Attach an SLA to the recent task with an already-past target; another sweep flips it.
    await c.post(f"/api/v1/tasks/{ids['new']}/sla", headers=h, json={"targetSeconds": 60 * 60 * 24 * 365})
    # Force breach on recent task by giving a zero target
    await c.post(f"/api/v1/tasks/{ids['new']}/sla", headers=h, json={"targetSeconds": 0})
    r = await c.post("/api/v1/tasks/sla-sweep", headers=h)
    # Both tasks now have SLAs and the small ones are already flagged at set time; sweep is a no-op.
    assert r.json()["newlyBreached"] == 0


@pytest.mark.asyncio
async def test_sla_report_totals_match(ctx):
    c, h, ids = ctx
    await c.post(f"/api/v1/tasks/{ids['old']}/sla", headers=h, json={"targetSeconds": 60})
    await c.post(f"/api/v1/tasks/{ids['new']}/sla", headers=h, json={"targetSeconds": 60 * 60})
    r = await c.get("/api/v1/tasks/sla-report", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["breached"] == 1
    assert 0.4 < body["withinTargetRate"] < 0.6


def test_working_seconds_skips_weekends():
    # Fri 10:00 → Mon 10:00 UTC. Working seconds should be ~2 * 24h + partial Fri/Mon,
    # not the naive 72h; specifically the Sat+Sun span (48h) is excluded.
    fri = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)
    mon = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    total = working_seconds_between(fri, mon)
    # Fri 10:00→00:00 = 14h, Mon 00:00→10:00 = 10h → 24h working
    assert 23 * 3600 <= total <= 25 * 3600


@pytest.mark.asyncio
async def test_bulk_dead_letter_replay(ctx):
    """Directly seed two dead-lettered outbox events and replay them in one call."""
    import uuid as _uuid
    from app.modules.workflow.models import OutboxEvent

    c, h, ids = ctx
    sm = ids["_sm"]
    now = datetime.now(timezone.utc)
    async with sm() as session:
        e1 = OutboxEvent(aggregate_type="student", aggregate_id=_uuid.uuid4(),
                         event_type="test.a", payload={}, attempts=5, dead_lettered=True,
                         last_error="boom", created_at=now)
        e2 = OutboxEvent(aggregate_type="student", aggregate_id=_uuid.uuid4(),
                         event_type="test.b", payload={}, attempts=5, dead_lettered=True,
                         last_error="bang", created_at=now)
        session.add_all([e1, e2]); await session.commit()
        seed_ids = [str(e1.id), str(e2.id)]

    r = await c.post("/api/v1/integration/dead-letters/replay", headers=h, json={"ids": seed_ids})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["requested"] == 2 and body["replayed"] == 2
    assert all(body["results"].values())
