"""Progression: milestone generation, submit, and panel decision (BE-1.7).

Key behaviour (arch §8.8): a continuing decision generates the next milestone; a terminating
one does not.
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
from app.db.session import get_session
from app.main import app
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.progression.models import MilestoneDefinition
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student

PERMS = ["student.read", "progression.read", "progression.decide", "admin.configure"]


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def ctx(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        perms = [Permission(code=c) for c in PERMS]
        s.add_all(perms); await s.flush()
        role = Role(name="PGR Administrator")   # unrestricted student scope
        s.add(role); await s.flush(); await s.refresh(role, ["permissions"]); role.permissions = perms
        user = User(email="u@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]

        prog = Programme(name="PhD", code="PHD")
        s.add(prog); await s.flush()
        s.add_all([
            MilestoneDefinition(programme_id=prog.id, name="Induction", due_offset_days=30),
            MilestoneDefinition(programme_id=prog.id, name="Confirmation", due_offset_days=270),
        ])
        person = Person(given_name="Sam", family_name="R")
        s.add(person); await s.flush()
        student = Student(
            person_id=person.id, student_ref="PGR-X", programme_id=prog.id,
            start_date=date(2024, 1, 1), study_mode=StudyMode.full_time, status=StudentStatus.registered,
        )
        s.add(student); await s.commit()
        sid = str(student.id)

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/v1/auth/login", json={"email": "u@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield client, h, sid
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_first_milestone_is_generated(ctx):
    client, h, sid = ctx
    r = await client.get(f"/api/v1/students/{sid}/milestones", headers=h)
    assert r.status_code == 200
    ms = r.json()
    assert len(ms) == 1
    assert ms[0]["name"] == "Induction"


@pytest.mark.asyncio
async def test_submit_then_decide_generates_next(ctx):
    client, h, sid = ctx
    m = (await client.get(f"/api/v1/students/{sid}/milestones", headers=h)).json()[0]

    r = await client.post(f"/api/v1/milestones/{m['id']}/submit", headers=h, json={"studentSubmissionRef": "doc-1"})
    assert r.status_code == 200 and r.json()["status"] == "submitted"

    r = await client.post(f"/api/v1/milestones/{m['id']}/decide", headers=h, json={"outcome": "progress", "rationale": "good"})
    assert r.status_code == 200 and r.json()["status"] == "decided"

    # Next milestone (Confirmation) was generated.
    ms = (await client.get(f"/api/v1/students/{sid}/milestones", headers=h)).json()
    names = sorted(x["name"] for x in ms)
    assert names == ["Confirmation", "Induction"]


@pytest.mark.asyncio
async def test_terminating_decision_generates_no_next(ctx):
    client, h, sid = ctx
    m = (await client.get(f"/api/v1/students/{sid}/milestones", headers=h)).json()[0]
    r = await client.post(f"/api/v1/milestones/{m['id']}/decide", headers=h, json={"outcome": "withdraw"})
    assert r.status_code == 200
    ms = (await client.get(f"/api/v1/students/{sid}/milestones", headers=h)).json()
    assert len(ms) == 1  # no next milestone


@pytest.mark.asyncio
async def test_cannot_decide_twice(ctx):
    client, h, sid = ctx
    m = (await client.get(f"/api/v1/students/{sid}/milestones", headers=h)).json()[0]
    await client.post(f"/api/v1/milestones/{m['id']}/decide", headers=h, json={"outcome": "progress"})
    r = await client.post(f"/api/v1/milestones/{m['id']}/decide", headers=h, json={"outcome": "progress"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "workflow_error"
