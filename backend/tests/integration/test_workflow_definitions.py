"""Configurable workflow definitions + instances (BE-2.1, arch §9.1)."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.modules.identity.models import Permission, Role, User

DEF = {
    "key": "onboarding", "name": "Onboarding", "initialState": "pending",
    "states": ["pending", "in_progress", "complete"],
    "transitions": [
        {"from": "pending", "on": "start", "to": "in_progress",
         "action": {"createTask": {"title": "Checklist", "assigneeRole": "PGR Administrator"}}},
        {"from": "in_progress", "on": "finish", "to": "complete"},
    ],
    "activate": True,
}


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
async def test_define_start_and_advance(client):
    d = (await client.post("/api/v1/workflow-definitions", json=DEF)).json()
    assert d["active"] is True and d["version"] == 1

    inst = (await client.post("/api/v1/workflow-instances", json={
        "key": "onboarding", "aggregateType": "student", "aggregateId": str(uuid.uuid4()),
    })).json()
    assert inst["currentState"] == "pending"

    inst = (await client.post(f"/api/v1/workflow-instances/{inst['id']}/events", json={"event": "start"})).json()
    assert inst["currentState"] == "in_progress"
    inst = (await client.post(f"/api/v1/workflow-instances/{inst['id']}/events", json={"event": "finish"})).json()
    assert inst["currentState"] == "complete"


@pytest.mark.asyncio
async def test_invalid_transition_rejected(client):
    await client.post("/api/v1/workflow-definitions", json=DEF)
    inst = (await client.post("/api/v1/workflow-instances", json={
        "key": "onboarding", "aggregateType": "student", "aggregateId": str(uuid.uuid4()),
    })).json()
    r = await client.post(f"/api/v1/workflow-instances/{inst['id']}/events", json={"event": "finish"})
    assert r.status_code == 422  # can't finish from 'pending'


@pytest.mark.asyncio
async def test_new_version_deactivates_previous(client):
    v1 = (await client.post("/api/v1/workflow-definitions", json=DEF)).json()
    v2 = (await client.post("/api/v1/workflow-definitions", json=DEF)).json()
    assert v2["version"] == 2 and v2["active"] is True
    defs = {d["version"]: d for d in (await client.get("/api/v1/workflow-definitions")).json()}
    assert defs[1]["active"] is False and defs[2]["active"] is True
