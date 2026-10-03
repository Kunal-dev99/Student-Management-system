"""DW-2 — scheduled publications, runs and watermarks, through the API (SQLite)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.core.tenant_context import DEFAULT_TENANT_ID, tenant_scope
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.models import Department
from app.modules.tenant.models import Tenant
from app.modules.warehouse import service as warehouse_service
from app.modules.warehouse.models import WarehousePublication, WarehouseWatermark
from app.modules.warehouse.service import PublicationService, next_run
from app.modules.warehouse.targets import LocalTarget

OLD = datetime(2026, 9, 1, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def ctx(tmp_path, monkeypatch):
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        s.add(Tenant(id=DEFAULT_TENANT_ID, name="Default", subdomain="default", activated_at=OLD))
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        admin = Role(name="Institution Administrator"); reader = Role(name="Executive")
        s.add_all([admin, reader]); await s.flush()
        await s.refresh(admin, ["permissions"]); admin.permissions = list(perms.values())
        await s.refresh(reader, ["permissions"]); reader.permissions = [perms["reporting.read"]]
        for email, role in (("admin@inst.example.com", admin), ("exec@inst.example.com", reader)):
            u = User(email=email, password_hash=hash_password("pw"), is_active=True)
            s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]
        for i in range(3):
            s.add(Person(given_name=f"G{i}", family_name="F", updated_at=OLD))
        s.add(Department(name="Oncology", code="ONC", updated_at=OLD))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    target = LocalTarget(str(tmp_path))
    monkeypatch.setattr("app.modules.warehouse.targets.default_target", lambda: target)
    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        tokens = {}
        for who in ("admin", "exec"):
            r = await c.post("/api/v1/auth/login", json={"email": f"{who}@inst.example.com", "password": "pw"})
            tokens[who] = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, tokens, sm, tmp_path
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_create_validate_and_permissions(ctx):
    c, h, _, _ = ctx
    body = {"name": "Nightly", "objects": ["person", "department"], "fileFormat": "csv"}
    r = await c.post("/api/v1/warehouse/publications", headers=h["admin"], json=body)
    assert r.status_code == 201, r.text
    assert r.json()["nextRunAt"] and r.json()["personalData"] is False
    assert (await c.post("/api/v1/warehouse/publications", headers=h["admin"], json=body)).status_code == 409
    bad = await c.post("/api/v1/warehouse/publications", headers=h["admin"], json={"name": "X", "objects": ["nope"]})
    assert bad.status_code in (400, 422) and "nope" in bad.text
    assert (await c.post("/api/v1/warehouse/publications", headers=h["exec"], json={"name": "Y"})).status_code == 403
    assert (await c.get("/api/v1/warehouse/publications", headers=h["exec"])).status_code == 200
    cat = (await c.get("/api/v1/warehouse/catalogue", headers=h["exec"])).json()
    person = next(o for o in cat if o["name"] == "person")
    assert "email" in person["personalColumns"] and all(col["name"] != "email" for col in person["columns"])


@pytest.mark.asyncio
async def test_first_run_full_then_incremental_with_watermarks(ctx):
    c, h, sm, root = ctx
    pub = (await c.post("/api/v1/warehouse/publications", headers=h["admin"],
                        json={"name": "Nightly", "objects": ["person", "department"], "fileFormat": "csv"})).json()
    first = (await c.post(f"/api/v1/warehouse/publications/{pub['id']}/run", headers=h["admin"])).json()
    assert first["status"] == "succeeded", first["error"]
    assert first["mode"] == "full" and first["rows"] == 4
    manifest = json.loads((Path(first["location"]) / "manifest.json").read_text())
    assert manifest["runId"] == first["id"]

    second = (await c.post(f"/api/v1/warehouse/publications/{pub['id']}/run", headers=h["admin"])).json()
    assert second["status"] == "succeeded" and second["mode"] == "incremental"
    assert second["rows"] == 0   # nothing changed since the first run (rows were stamped long before)
    async with tenant_scope(DEFAULT_TENANT_ID), sm() as s:
        marks = {m.object_name: m.high_water for m in (await s.execute(select(WarehouseWatermark))).scalars()}
    assert set(marks) == {"person", "department"}
    runs = (await c.get(f"/api/v1/warehouse/publications/{pub['id']}/runs", headers=h["exec"])).json()
    assert [r["mode"] for r in runs] == ["incremental", "full"]


@pytest.mark.asyncio
async def test_a_failed_run_keeps_its_place(ctx, monkeypatch):
    c, h, sm, _ = ctx
    pub = (await c.post("/api/v1/warehouse/publications", headers=h["admin"],
                        json={"name": "Nightly", "objects": ["department"], "fileFormat": "csv"})).json()

    class Broken:
        def put(self, *a, **k):
            raise OSError("bucket unreachable")

        def location(self, prefix):
            return prefix

    monkeypatch.setattr("app.modules.warehouse.targets.default_target", lambda: Broken())
    failed = (await c.post(f"/api/v1/warehouse/publications/{pub['id']}/run", headers=h["admin"])).json()
    assert failed["status"] == "failed" and "bucket unreachable" in failed["error"]
    async with tenant_scope(DEFAULT_TENANT_ID), sm() as s:
        assert (await s.execute(select(WarehouseWatermark))).first() is None
        assert (await s.get(WarehousePublication, uuid.UUID(pub["id"]))).last_full_at is None


@pytest.mark.asyncio
async def test_the_worker_runs_due_publications(ctx):
    c, h, sm, _ = ctx
    pub = (await c.post("/api/v1/warehouse/publications", headers=h["admin"],
                        json={"name": "Hourly", "objects": ["department"], "frequency": "hourly"})).json()
    async with tenant_scope(DEFAULT_TENANT_ID), sm() as s:
        p = await s.get(WarehousePublication, uuid.UUID(pub["id"]))
        p.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await s.commit()
        runs = await PublicationService(s).run_due()
        assert [r.triggered_by for r in runs] == ["schedule"] and runs[0].status == "succeeded"
        p = await s.get(WarehousePublication, p.id)
        assert warehouse_service._aware(p.next_run_at) > datetime.now(timezone.utc)
        assert await PublicationService(s).run_due() == []


def test_next_run_schedule():
    p = WarehousePublication(frequency="daily", run_at_hour=2)
    assert next_run(p, datetime(2026, 10, 3, 1, 0, tzinfo=timezone.utc)) == datetime(2026, 10, 3, 2, tzinfo=timezone.utc)
    assert next_run(p, datetime(2026, 10, 3, 2, 0, tzinfo=timezone.utc)) == datetime(2026, 10, 4, 2, tzinfo=timezone.utc)
    p.frequency = "hourly"
    assert next_run(p, datetime(2026, 10, 3, 2, 30, tzinfo=timezone.utc)) == datetime(2026, 10, 3, 3, tzinfo=timezone.utc)
