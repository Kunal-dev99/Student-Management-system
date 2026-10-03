"""Regulatory updates under subscription (Demo 2 item 1.21): version list, rollback, release impact."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.core.tenant_context import DEFAULT_TENANT_ID, tenant_scope
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.exports import spec_release
from app.modules.exports.constants import SpecVersionStatus
from app.modules.exports.models import ReportProfile, StatutorySpecVersion
from app.modules.identity.constants import EXCLUSIVE_PERMISSIONS, PERMISSIONS
from app.modules.identity.models import Permission, Role, User

PACK, YEAR = "HESA_STUDENT", "2026/27"


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        platform = Role(name="dev"); inst = Role(name="Institution Administrator")
        s.add_all([platform, inst]); await s.flush()
        await s.refresh(platform, ["permissions"]); platform.permissions = list(perms.values())
        await s.refresh(inst, ["permissions"])
        inst.permissions = [p for c, p in perms.items() if c not in EXCLUSIVE_PERMISSIONS]
        for email, role in (("platform@vendor.example.com", platform), ("admin@inst.example.com", inst)):
            u = User(email=email, password_hash=hash_password("pw"), is_active=True)
            s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]
        s.add(StatutorySpecVersion(pack_code=PACK, academic_year=YEAR, version=2, name="v2",
                                   status=SpecVersionStatus.superseded, fields=[], rules=[]))
        s.add(StatutorySpecVersion(pack_code=PACK, academic_year=YEAR, version=3, name="v3",
                                   status=SpecVersionStatus.active, fields=[], rules=[]))
        s.add(ReportProfile(code=PACK, name="HESA Student return", academic_year=YEAR))
        s.add(ReportProfile(code=PACK, name="Last year's return", academic_year="2025/26"))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        tokens = {}
        for who, email in (("platform", "platform@vendor.example.com"), ("inst", "admin@inst.example.com")):
            r = await c.post("/api/v1/auth/login", json={"email": email, "password": "pw"})
            tokens[who] = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, tokens, sm
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_rollback_is_platform_only_and_reversible(ctx):
    c, h, _ = ctx
    url = "/api/v1/report-advisories/spec-versions"
    versions = (await c.get(url, headers=h["inst"], params={"packCode": PACK, "academicYear": YEAR})).json()
    assert [(v["version"], v["status"]) for v in versions] == [(3, "active"), (2, "superseded")]
    v2 = next(v["id"] for v in versions if v["version"] == 2)
    v3 = next(v["id"] for v in versions if v["version"] == 3)

    assert (await c.post(f"{url}/{v2}/restore", headers=h["inst"])).status_code == 403
    r = await c.post(f"{url}/{v2}/restore", headers=h["platform"])
    assert r.status_code == 200 and r.json()["status"] == "active"
    after = (await c.get(url, headers=h["inst"], params={"packCode": PACK, "academicYear": YEAR})).json()
    assert [(v["version"], v["status"]) for v in after] == [(3, "superseded"), (2, "active")]
    await c.post(f"{url}/{v3}/restore", headers=h["platform"])      # undo the rollback
    again = (await c.get(url, headers=h["inst"], params={"packCode": PACK, "academicYear": YEAR})).json()
    assert [v["status"] for v in again] == ["active", "superseded"]


@pytest.mark.asyncio
async def test_impact_lists_the_institutions_returns_on_that_pack_and_year(ctx):
    _, _, sm = ctx
    async with tenant_scope(DEFAULT_TENANT_ID), sm() as s:
        rows = await spec_release.impact(s, PACK, YEAR)
    assert [r["profile"] for r in rows] == ["HESA Student return"]      # other years ignored
    assert rows[0]["ready"] is False and rows[0]["signedOff"] is False
    assert isinstance(rows[0]["missing"], list)
