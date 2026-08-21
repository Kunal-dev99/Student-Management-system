"""Funding arrangements over time (BE-1.8).

A change closes the current arrangement and opens a new one, preserving history (arch §8.9).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.modules.funding.models import FundingSource
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Student

PERMS = ["student.read", "funding.read", "funding.change"]


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
        role = Role(name="PGR Administrator")
        s.add(role); await s.flush(); await s.refresh(role, ["permissions"]); role.permissions = perms
        user = User(email="u@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]
        src = FundingSource(name="UKRI", funder_type="research_council")
        person = Person(given_name="Sam", family_name="R")
        s.add_all([src, person]); await s.flush()
        student = Student(person_id=person.id, student_ref="PGR-F", study_mode=StudyMode.full_time, status=StudentStatus.registered)
        s.add(student); await s.commit()
        ids = {"student": str(student.id), "source": str(src.id)}

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/v1/auth/login", json={"email": "u@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield client, h, ids
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_and_list_funding(ctx):
    client, h, ids = ctx
    r = await client.post(
        f"/api/v1/students/{ids['student']}/funding", headers=h,
        json={"fundingType": "research_council", "fundingSourceId": ids["source"], "stipendAmount": "19000.00", "currency": "GBP"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "active"
    assert body["fundingSourceName"] == "UKRI"

    r = await client.get(f"/api/v1/students/{ids['student']}/funding", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_change_preserves_history(ctx):
    client, h, ids = ctx
    first = (await client.post(
        f"/api/v1/students/{ids['student']}/funding", headers=h,
        json={"fundingType": "research_council", "stipendAmount": "19000", "currency": "GBP"},
    )).json()

    r = await client.post(
        f"/api/v1/funding/{first['id']}/change", headers=h,
        json={"fundingType": "university_scholarship", "stipendAmount": "21000", "currency": "GBP"},
    )
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["status"] == "active" and new["validTo"] is None

    arrangements = (await client.get(f"/api/v1/students/{ids['student']}/funding", headers=h)).json()
    assert len(arrangements) == 2
    by_status = {a["status"]: a for a in arrangements}
    assert by_status["changed"]["validTo"] is not None      # old one closed
    assert by_status["active"]["fundingType"] == "university_scholarship"


@pytest.mark.asyncio
async def test_end_funding(ctx):
    client, h, ids = ctx
    a = (await client.post(
        f"/api/v1/students/{ids['student']}/funding", headers=h,
        json={"fundingType": "self_funded"},
    )).json()
    r = await client.post(f"/api/v1/funding/{a['id']}/end", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "ended" and r.json()["validTo"] is not None
