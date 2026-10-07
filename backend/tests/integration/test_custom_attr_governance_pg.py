"""Custom attribute governance, Phase 7 — Postgres-only release-gate checks.

Run against the configured Postgres database (skipped on SQLite). Everything it creates is under a
unique key prefix and removed afterwards, through the explicit bypass.

- every governance table is tenant-owned with forced, fail-closed row-level security
- a tenant can't read another tenant's attributes, requests, decisions, checks or usage, and
  can't write a row into another tenant
- two approvers deciding the same request at the same moment: exactly one wins (row lock),
  the other is refused — never two decisions
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.errors import ConflictError
from app.core.principal import Principal
from app.core.tenant_context import system_scope, tenant_scope

pytestmark = pytest.mark.asyncio

TABLES = ("student_custom_field", "student_custom_field_event", "student_custom_field_assessment",
          "student_custom_field_usage", "student_custom_value")
PREFIX = f"zz_gate_{uuid.uuid4().hex[:6]}"


@pytest.fixture
async def pg():
    url = get_settings().database_url
    if not url.startswith("postgresql"):
        pytest.skip("Postgres-only (row-level security, row locks)")
    eng = create_async_engine(url, poolclass=NullPool)
    try:
        async with eng.connect() as conn:
            has = (await conn.execute(text(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = 'student_custom_field_usage'"
            ))).scalar_one()
        if not has:
            pytest.skip("database not migrated to ca3")
    except OSError:
        pytest.skip("Postgres not reachable")
    sm = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    yield eng, sm
    async with system_scope(), sm() as s:      # clean up everything this module created
        await s.execute(text("DELETE FROM student_custom_field_event WHERE field_key LIKE :p").bindparams(p=f"{PREFIX}%"))
        await s.execute(text("DELETE FROM student_custom_field WHERE key LIKE :p").bindparams(p=f"{PREFIX}%"))
        await s.commit()
    await eng.dispose()


async def _two_tenants(sm) -> tuple[uuid.UUID, uuid.UUID]:
    async with system_scope(), sm() as s:
        ids = (await s.execute(text("SELECT id FROM tenant ORDER BY id LIMIT 2"))).scalars().all()
    if len(ids) < 2:
        pytest.skip("needs two tenants")
    return ids[0], ids[1]


async def test_every_governance_table_has_forced_fail_closed_rls(pg):
    eng, _ = pg
    from app.db.tenant_guard import check_database

    async with eng.connect() as conn:
        rows = {r[0]: (r[1], r[2]) for r in (await conn.execute(text(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(:t)"
        ).bindparams(t=list(TABLES)))).all()}
        problems = [p for p in await check_database(conn) if p.split(":")[0] in TABLES]
    assert set(rows) == set(TABLES)
    assert all(enabled and forced for enabled, forced in rows.values()), rows
    assert problems == []


async def test_tenants_cannot_see_or_write_each_others_attributes(pg):
    _, sm = pg
    a, b = await _two_tenants(sm)
    key = f"{PREFIX}_iso"
    async with tenant_scope(a), sm() as s:
        fid = (await s.execute(text(
            "INSERT INTO student_custom_field (id, tenant_id, key, label, data_type, track_history, reason, status, "
            "created_at, updated_at) VALUES (gen_random_uuid(), :t, :k, 'Gate', 'code', false, 'gate', 'pending', now(), now()) "
            "RETURNING id").bindparams(t=a, k=key))).scalar_one()
        for sql in (
            "INSERT INTO student_custom_field_event (id, tenant_id, custom_field_id, field_key, field_label, action, created_at) "
            "VALUES (gen_random_uuid(), :t, :f, :k, 'Gate', 'requested', now())",
            "INSERT INTO student_custom_field_assessment (id, tenant_id, custom_field_id, verdict, result, created_at) "
            "VALUES (gen_random_uuid(), :t, :f, 'supported', '{}', now())",
            "INSERT INTO student_custom_field_usage (id, tenant_id, custom_field_id, profile_code, academic_year, purpose, "
            "row_count, used_at) VALUES (gen_random_uuid(), :t, :f, 'HESA', '2026/27', 'generate', 1, now())",
        ):
            await s.execute(text(sql).bindparams(t=a, f=fid, **({"k": key} if ":k" in sql else {})))
        await s.commit()

    counts = {
        "student_custom_field": "SELECT count(*) FROM student_custom_field WHERE id = :f",
        "student_custom_field_event": "SELECT count(*) FROM student_custom_field_event WHERE custom_field_id = :f",
        "student_custom_field_assessment": "SELECT count(*) FROM student_custom_field_assessment WHERE custom_field_id = :f",
        "student_custom_field_usage": "SELECT count(*) FROM student_custom_field_usage WHERE custom_field_id = :f",
    }

    async def seen(tenant) -> dict:
        async with tenant_scope(tenant), sm() as s:
            return {t: (await s.execute(text(q).bindparams(f=fid))).scalar_one() for t, q in counts.items()}

    assert set((await seen(a)).values()) == {1}
    assert set((await seen(b)).values()) == {0}
    async with sm() as s:                      # no tenant at all: fail-closed
        assert (await s.execute(text(counts["student_custom_field"]).bindparams(f=fid))).scalar_one() == 0

    # Tenant B can't plant a row in tenant A (WITH CHECK), nor change A's attribute.
    with pytest.raises(Exception, match="row-level security"):
        async with tenant_scope(b), sm() as s:
            await s.execute(text(
                "INSERT INTO student_custom_field (id, tenant_id, key, label, data_type, track_history, reason, status, "
                "created_at, updated_at) VALUES (gen_random_uuid(), :t, :k, 'X', 'code', false, 'x', 'active', now(), now())"
            ).bindparams(t=a, k=f"{PREFIX}_plant"))
            await s.commit()
    async with tenant_scope(b), sm() as s:
        changed = (await s.execute(text("UPDATE student_custom_field SET status = 'active' WHERE id = :f")
                                   .bindparams(f=fid))).rowcount
        await s.commit()
    assert changed == 0


async def test_concurrent_approvals_produce_exactly_one_decision(pg):
    _, sm = pg
    from app.modules.student_record.custom_fields import CustomFieldService

    tenant, _ = await _two_tenants(sm)
    async with system_scope(), sm() as s:
        users = (await s.execute(text("SELECT id, email FROM users WHERE tenant_id = :t ORDER BY email LIMIT 2")
                                 .bindparams(t=tenant))).all()
    if len(users) < 2:
        pytest.skip("needs two users in the tenant")
    approvers = [Principal(user_id=u.id, email=u.email, tenant_id=tenant) for u in users]

    async with tenant_scope(tenant), sm() as s:
        fid = (await s.execute(text(
            "INSERT INTO student_custom_field (id, tenant_id, key, label, data_type, track_history, reason, status, "
            "created_at, updated_at) VALUES (gen_random_uuid(), :t, :k, 'Race', 'code', false, 'gate', 'pending', now(), now()) "
            "RETURNING id").bindparams(t=tenant, k=f"{PREFIX}_race"))).scalar_one()
        await s.commit()

    async def decide(p: Principal):
        async with tenant_scope(tenant), sm() as s:
            try:
                f = await CustomFieldService(s).approve(fid, principal=p, reason=f"by {p.email}")
                return ("approved", f.decided_by_user_id)
            except ConflictError as exc:
                return ("refused", str(exc))

    results = await asyncio.gather(*(decide(p) for p in approvers))
    outcomes = sorted(r[0] for r in results)
    assert outcomes == ["approved", "refused"], results
    async with tenant_scope(tenant), sm() as s:
        decided = (await s.execute(text(
            "SELECT count(*) FROM student_custom_field_event WHERE custom_field_id = :f AND action = 'approved'"
        ).bindparams(f=fid))).scalar_one()
        status = (await s.execute(text("SELECT status FROM student_custom_field WHERE id = :f").bindparams(f=fid))).scalar_one()
    assert decided == 1 and status == "approved"
