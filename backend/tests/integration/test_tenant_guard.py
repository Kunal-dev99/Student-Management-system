"""T2 — tenant isolation guarantees on the real, migrated Postgres database.

  * Guard: every tenant table has forced RLS, a compulsory tenant column and exactly the two
    T1 policies; every other table is listed as deliberately global. Removing one policy is
    caught (proved below inside a rolled-back transaction).
  * Fail-closed: with no tenant set, every tenant table returns zero rows.
  * Connection reuse: a tenant set for one unit of work never carries into the next one on
    the same pooled connection — including after an error.

Skipped unless the configured database is Postgres and migrated to t1_tenant_hardening or
later. Read-only: nothing is committed. Run them on a fresh copy with
``python scripts/run_tenant_leak_tests.py``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.tenant_context import system_scope, tenant_scope
from app.db.tenant_guard import check_database, tenant_tables


async def _skip_unless_t1(eng) -> None:
    try:
        async with eng.connect() as conn:
            hardened = await conn.scalar(text(
                "SELECT count(*) FROM pg_policies WHERE policyname = 'tenant_isolation_system'"
            ))
    except Exception:
        pytest.skip("PostgreSQL not reachable")
    if not hardened:
        pytest.skip("Database not migrated to t1_tenant_hardening yet "
                    "(run scripts/run_tenant_leak_tests.py to test on a migrated copy)")


@pytest_asyncio.fixture
async def engine():
    url = get_settings().database_url
    if not url.startswith("postgresql"):
        pytest.skip("Tenant isolation is enforced by Postgres; skipped on other dialects")
    eng = create_async_engine(url, poolclass=NullPool)
    try:
        await _skip_unless_t1(eng)
        yield eng
    finally:
        await eng.dispose()


async def _tenant_ids(conn) -> list[uuid.UUID]:
    # The tenant registry is global, so no bypass is needed.
    return [r[0] for r in await conn.execute(text("SELECT id FROM tenant ORDER BY created_at, id"))]


# --------------------------------------------------------------------------------------------
# Guard
# --------------------------------------------------------------------------------------------

async def test_every_table_is_protected(engine):
    async with engine.connect() as conn:
        problems = await check_database(conn)
    assert problems == [], "Unprotected tables:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("break_it, expected", [
    ("DROP POLICY tenant_isolation ON student", "student: missing policy tenant_isolation"),
    ("ALTER TABLE student NO FORCE ROW LEVEL SECURITY", "student: row-level security is not forced"),
    ("ALTER TABLE student ALTER COLUMN tenant_id DROP NOT NULL", "student: tenant_id allows NULL"),
    ("CREATE POLICY open_door ON student USING (true)", "student: unexpected policy 'open_door'"),
    ("CREATE TABLE t2_unscoped (id int)", "t2_unscoped: no tenant_id and not listed in GLOBAL_TABLES"),
])
async def test_guard_catches_a_weakened_table(engine, break_it, expected):
    """Deliberately weaken one table and the guard must report it. DDL is transactional in
    Postgres, so the change is rolled back and nothing is left behind."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text(break_it))
            problems = await check_database(conn)
        finally:
            await trans.rollback()
    assert any(p.startswith(expected) for p in problems), problems


# --------------------------------------------------------------------------------------------
# Fail-closed
# --------------------------------------------------------------------------------------------

async def test_no_tenant_means_no_rows_in_any_table(engine):
    async with engine.connect() as conn:
        tables = await tenant_tables(conn)
        await conn.commit()
        assert len(tables) > 100

        async with conn.begin():
            await conn.execute(text("SELECT set_config('app.bypass_tenant', 'on', true)"))
            populated = [t for t in tables if await conn.scalar(text(f'SELECT count(*) FROM "{t}"'))]
        # Non-vacuous: there is data to hide.
        assert "student" in populated

        unknown = str(uuid.uuid4())
        for context in ("", unknown):
            async with conn.begin():
                await conn.execute(text("SELECT set_config('app.current_tenant', :t, true)")
                                   .bindparams(t=context))
                visible = {t: await conn.scalar(text(f'SELECT count(*) FROM "{t}"')) for t in populated}
            leaking = {t: n for t, n in visible.items() if n}
            assert leaking == {}, f"rows visible with tenant={context or 'unset'}: {leaking}"


async def test_no_tenant_means_writes_are_refused(engine):
    async with engine.connect() as conn:
        tid = (await _tenant_ids(conn))[0]
        await conn.commit()
        trans = await conn.begin()
        try:
            with pytest.raises(Exception, match="row-level security"):
                await conn.execute(text(
                    "INSERT INTO department (id, tenant_id, code, name) "
                    "VALUES (gen_random_uuid(), :t, 'T2X', 'T2 probe')"
                ).bindparams(t=tid))
        finally:
            await trans.rollback()


# --------------------------------------------------------------------------------------------
# Connection reuse
# --------------------------------------------------------------------------------------------

async def test_tenant_does_not_carry_over_on_a_reused_connection():
    url = get_settings().database_url
    if not url.startswith("postgresql"):
        pytest.skip("Postgres only")
    # One pooled connection, so every unit of work below reuses the same backend.
    eng = create_async_engine(url, pool_size=1, max_overflow=0)
    Session = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    try:
        await _skip_unless_t1(eng)
        async with eng.connect() as conn:
            tid = (await _tenant_ids(conn))[0]

        async def probe() -> tuple[int, str, int]:
            async with Session() as s:
                row = (await s.execute(text(
                    "SELECT pg_backend_pid(), coalesce(current_setting('app.current_tenant', true), ''), "
                    "(SELECT count(*) FROM student)"
                ))).one()
                return row[0], row[1], row[2]

        async with tenant_scope(tid):
            pid, seen, students = await probe()
        assert seen == str(tid) and students > 0

        # Same connection, no tenant: nothing carried over.
        pid2, seen2, students2 = await probe()
        assert (pid2, seen2, students2) == (pid, "", 0)

        # A unit of work that fails part-way must not leave its tenant behind either.
        with pytest.raises(RuntimeError):
            async with tenant_scope(tid):
                async with Session() as s:
                    await s.execute(text("SELECT 1"))
                    raise RuntimeError("request failed")
        pid3, seen3, students3 = await probe()
        assert (pid3, seen3, students3) == (pid, "", 0)

        # Session-level (not transaction-local) settings would survive; prove the bypass
        # set inside system_scope does not either.
        async with system_scope():
            await probe()
        async with Session() as s:
            bypass = await s.scalar(text("SELECT coalesce(current_setting('app.bypass_tenant', true), '')"))
        assert bypass == ""

        # Raw Core connections are not published to: they get no tenant, so no rows.
        async with tenant_scope(tid):
            async with eng.connect() as conn:
                assert await conn.scalar(text("SELECT count(*) FROM student")) == 0
    finally:
        await eng.dispose()
