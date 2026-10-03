"""DW-3 — consumers, the OAuth client-credentials grant, and the pull API (SQLite)."""
from __future__ import annotations

import base64
import csv
import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.core.tenant_context import DEFAULT_TENANT_ID
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.models import Department
from app.modules.tenant.models import Tenant
from app.modules.warehouse.models import WarehouseDeletedRow

OTHER = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
OLD = datetime(2026, 9, 1, tzinfo=timezone.utc)
TOKEN = "/api/v1/warehouse/oauth/token"


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        s.add_all([Tenant(id=DEFAULT_TENANT_ID, name="Default", subdomain="default", activated_at=OLD),
                   Tenant(id=OTHER, name="Other", subdomain="other", activated_at=OLD)])
        perms = [Permission(code=c) for c in PERMISSIONS]
        s.add_all(perms); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = perms
        for email, tid in (("admin@inst.example.com", DEFAULT_TENANT_ID), ("admin@other.example.com", OTHER)):
            u = User(email=email, password_hash=hash_password("pw"), is_active=True, tenant_id=tid)
            s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]
        for i in range(3):
            s.add(Person(given_name=f"G{i}", family_name="F", email=f"g{i}@inst.example.com", updated_at=OLD))
        s.add(Person(tenant_id=OTHER, given_name="Other", family_name="P", email="o@other.example.com", updated_at=OLD))
        s.add(Department(name="Oncology", code="ONC", updated_at=OLD))
        s.add(WarehouseDeletedRow(table_name="person", row_id=uuid.uuid4(), deleted_at=OLD + timedelta(days=1)))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        admins = {}
        for key, email in (("default", "admin@inst.example.com"), ("other", "admin@other.example.com")):
            r = await c.post("/api/v1/auth/login", json={"email": email, "password": "pw"})
            admins[key] = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, admins
    app.dependency_overrides.clear()
    await eng.dispose()


async def _consumer(c, admin, **body):
    r = await c.post("/api/v1/warehouse/consumers", headers=admin,
                     json={"name": "Loader", "objects": ["person", "department"], **body})
    assert r.status_code == 201, r.text
    return r.json()


async def _token(c, cons) -> dict:
    r = await c.post(TOKEN, data={"grant_type": "client_credentials", "client_id": cons["clientId"],
                                  "client_secret": cons["clientSecret"]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_token_grant_and_errors(ctx):
    c, admin = ctx
    cons = await _consumer(c, admin["default"])
    assert cons["clientId"].startswith("pgrw_") and len(cons["clientSecret"]) > 30
    listed = (await c.get("/api/v1/warehouse/consumers", headers=admin["default"])).json()
    assert "clientSecret" not in listed[0]

    bad = await c.post(TOKEN, data={"grant_type": "password", "client_id": cons["clientId"], "client_secret": "x"})
    assert bad.status_code == 400 and bad.json()["error"] == "unsupported_grant_type"
    wrong = await c.post(TOKEN, data={"grant_type": "client_credentials", "client_id": cons["clientId"],
                                      "client_secret": "wrong"})
    assert wrong.status_code == 401 and wrong.json()["error"] == "invalid_client"
    basic = base64.b64encode(f"{cons['clientId']}:{cons['clientSecret']}".encode()).decode()
    ok = await c.post(TOKEN, data={"grant_type": "client_credentials"}, headers={"Authorization": f"Basic {basic}"})
    assert ok.status_code == 200 and ok.json()["token_type"] == "Bearer" and ok.json()["expires_in"] == 900


@pytest.mark.asyncio
async def test_reads_only_what_it_may_and_pages_cleanly(ctx):
    c, admin = ctx
    h = await _token(c, await _consumer(c, admin["default"]))
    cat = (await c.get("/api/v1/warehouse/data/objects", headers=h)).json()
    assert [o["name"] for o in cat] == ["person", "department"]
    assert (await c.get("/api/v1/warehouse/data/objects/student", headers=h)).status_code == 403
    assert (await c.get("/api/v1/warehouse/data/objects/nope", headers=h)).status_code == 404

    seen, cursor = [], None
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = (await c.get("/api/v1/warehouse/data/objects/person", headers=h, params=params)).json()
        seen += page["rows"]
        cursor = page["nextCursor"]
        if not cursor:
            break
    assert len(seen) == 3 and len({r["id"] for r in seen}) == 3          # this institution only
    assert all("email" not in r for r in seen) and "_changed_at" in seen[0]

    later = (OLD + timedelta(days=2)).isoformat()
    assert (await c.get("/api/v1/warehouse/data/objects/person", headers=h, params={"changedSince": later})).json()["rows"] == []
    gone = (await c.get("/api/v1/warehouse/data/objects/person/deleted", headers=h,
                        params={"changedSince": OLD.isoformat()})).json()
    assert len(gone["rows"]) == 1
    as_csv = await c.get("/api/v1/warehouse/data/objects/department", headers=h, params={"format": "csv"})
    assert as_csv.headers["content-type"].startswith("text/csv") and "X-Window-To" in as_csv.headers
    assert list(csv.DictReader(io.StringIO(as_csv.text)))[0]["code"] == "ONC"


@pytest.mark.asyncio
async def test_personal_data_only_when_granted(ctx):
    c, admin = ctx
    h = await _token(c, await _consumer(c, admin["default"], name="Full", personalData=True))
    rows = (await c.get("/api/v1/warehouse/data/objects/person", headers=h)).json()["rows"]
    assert {r["email"] for r in rows} == {f"g{i}@inst.example.com" for i in range(3)}


@pytest.mark.asyncio
async def test_tokens_dont_cross_over_and_revoke_rotate_take_effect(ctx):
    c, admin = ctx
    cons = await _consumer(c, admin["default"])
    h = await _token(c, cons)
    assert (await c.get("/api/v1/students", headers=h)).status_code == 401                    # not a user token
    assert (await c.get("/api/v1/warehouse/data/objects", headers=admin["default"])).status_code == 401   # not a consumer token

    rotated = (await c.post(f"/api/v1/warehouse/consumers/{cons['id']}/rotate", headers=admin["default"])).json()
    old = await c.post(TOKEN, data={"grant_type": "client_credentials", "client_id": cons["clientId"],
                                    "client_secret": cons["clientSecret"]})
    assert old.status_code == 401
    h = await _token(c, {**cons, "clientSecret": rotated["clientSecret"]})
    assert (await c.get("/api/v1/warehouse/data/objects", headers=h)).status_code == 200
    await c.post(f"/api/v1/warehouse/consumers/{cons['id']}/revoke", headers=admin["default"])
    assert (await c.get("/api/v1/warehouse/data/objects", headers=h)).status_code == 401           # at once


@pytest.mark.asyncio
async def test_another_institutions_consumer_sees_only_its_own(ctx):
    c, admin = ctx
    h = await _token(c, await _consumer(c, admin["other"]))
    rows = (await c.get("/api/v1/warehouse/data/objects/person", headers=h)).json()["rows"]
    assert [r["id"] for r in rows] and len(rows) == 1
    assert (await c.get("/api/v1/warehouse/data/objects/department", headers=h)).json()["rows"] == []
