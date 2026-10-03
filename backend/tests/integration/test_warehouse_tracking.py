"""DW-1 on Postgres: the change tracking the incremental warehouse export relies on.

* Every published table (the T3 catalogue) has the update and delete triggers - a new catalogue
  object without them fails here.
* A plain SQL UPDATE stamps updated_at (not just ORM updates); a DELETE logs the row's id in
  warehouse_deleted_row under its own institution.
Runs in rolled-back transactions; skipped unless migrated to w1_warehouse.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.tenant_views import CATALOGUE


@pytest_asyncio.fixture
async def engine():
    url = get_settings().database_url
    if not url.startswith("postgresql"):
        pytest.skip("Postgres only")
    eng = create_async_engine(url, poolclass=NullPool)
    try:
        async with eng.connect() as conn:
            present = await conn.scalar(text("SELECT to_regclass('public.warehouse_deleted_row')"))
    except Exception:
        await eng.dispose()
        pytest.skip("PostgreSQL not reachable")
    if present is None:
        await eng.dispose()
        pytest.skip("Database not migrated to w1_warehouse yet")
    yield eng
    await eng.dispose()


async def test_every_published_table_has_both_triggers(engine):
    async with engine.connect() as conn:
        have = {(r[0], r[1]) for r in await conn.execute(text(
            "SELECT event_object_table, trigger_name FROM information_schema.triggers "
            "WHERE trigger_schema = 'public'"))}
    tables = sorted({o.table for o in CATALOGUE})
    missing = [(t, trig) for t in tables for trig in ("pgr_touch_updated_at", "pgr_log_deleted_row")
               if (t, trig) not in have]
    assert missing == [], f"published tables without change tracking: {missing}"


async def test_sql_update_stamps_and_delete_is_logged(engine):
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("SELECT set_config('app.bypass_tenant', 'on', true)"))
            tid = await conn.scalar(text("SELECT id FROM tenant ORDER BY created_at LIMIT 1"))
            dept = await conn.scalar(text(
                "INSERT INTO department (id, tenant_id, name, code, updated_at) "
                "VALUES (gen_random_uuid(), :t, 'DW probe', 'DWPROBE', '2000-01-01') RETURNING id"), {"t": tid})
            await conn.execute(text("UPDATE department SET name = 'DW probe 2' WHERE id = :d"), {"d": dept})
            stamped = await conn.scalar(text("SELECT updated_at > '2001-01-01' FROM department WHERE id = :d"), {"d": dept})
            assert stamped is True, "a plain SQL UPDATE must stamp updated_at"
            await conn.execute(text("DELETE FROM department WHERE id = :d"), {"d": dept})
            logged = (await conn.execute(text(
                "SELECT tenant_id, table_name FROM warehouse_deleted_row WHERE row_id = :d"), {"d": dept})).one()
            assert tuple(logged) == (tid, "department")
        finally:
            await trans.rollback()


async def test_history_tables_have_a_change_column(engine):
    async with engine.connect() as conn:
        nullable = {r[0]: r[1] for r in await conn.execute(text(
            "SELECT table_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'updated_at' AND table_name LIKE '%\\_history'"))}
    assert len(nullable) >= 12 and set(nullable.values()) == {"NO"}
