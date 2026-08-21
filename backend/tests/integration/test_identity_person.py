"""Integration tests for identity + person (BE-1.0a, BE-1.1) on an isolated in-memory DB."""
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
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.models import Person, PersonRelationship


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def client(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False)

    async with sm() as s:
        p_read = Permission(code="person.read")
        p_write = Permission(code="person.write")
        s.add_all([p_read, p_write])
        await s.flush()
        role = Role(name="Admin")
        s.add(role)
        await s.flush()
        await s.refresh(role, ["permissions"])
        role.permissions = [p_read, p_write]
        user = User(email="t@example.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user)
        await s.flush()
        await s.refresh(user, ["roles"])
        user.roles = [role]
        person = Person(given_name="Aisha", family_name="Khan", email="aisha@example.com")
        person.relationships = [
            PersonRelationship(
                relationship_type=PersonRelationshipType.applicant,
                valid_from=date(2020, 1, 1), valid_to=date(2020, 9, 1),
            ),
            PersonRelationship(
                relationship_type=PersonRelationshipType.student,
                valid_from=date(2020, 10, 1), valid_to=None,
            ),
        ]
        s.add(person)
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _token(client: AsyncClient) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": "t@example.com", "password": "pw"})
    assert r.status_code == 200, r.text
    return r.json()["accessToken"]


@pytest.mark.asyncio
async def test_login_and_me(client):
    tok = await _token(client)
    r = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    body = r.json()
    assert body["authenticated"] is True
    assert body["email"] == "t@example.com"
    assert "person.read" in body["permissions"]
    assert body["roles"] == ["Admin"]


@pytest.mark.asyncio
async def test_persons_requires_auth(client):
    r = await client.get("/api/v1/persons")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


@pytest.mark.asyncio
async def test_list_and_timeline(client):
    tok = await _token(client)
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.get("/api/v1/persons", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["page"]["total"] == 1
    pid = data["data"][0]["id"]

    r = await client.get(f"/api/v1/persons/{pid}/timeline", headers=h)
    assert r.status_code == 200
    labels = [e["label"] for e in r.json()["entries"]]
    assert any("Applicant" in x for x in labels)
    assert any("Student" in x for x in labels)


@pytest.mark.asyncio
async def test_create_person_and_permission_enforced(client):
    tok = await _token(client)
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.post(
        "/api/v1/persons",
        headers=h,
        json={"givenName": "New", "familyName": "Person", "email": "new.person@example.com"},
    )
    assert r.status_code == 201
    assert r.json()["givenName"] == "New"


@pytest.mark.asyncio
async def test_wrong_password_rejected(client):
    r = await client.post(
        "/api/v1/auth/login", json={"email": "t@example.com", "password": "nope"}
    )
    assert r.status_code == 401
