"""Tenant isolation in Postgres — the fail-closed policy pair shipped by T1.

RLS is a Postgres feature, so this test is skipped on the default SQLite suite. It runs against
the configured Postgres engine, in a throwaway schema it creates and drops, so it never touches
real data. It installs exactly the policies every tenant table carries (``tenant_ddl``) and
asserts:

  * no tenant set → no rows (fail-closed), for reads and writes;
  * a tenant sees only its own rows, and can't write a row for another tenant (WITH CHECK);
  * transaction-local context does not leak to the next transaction;
  * the owner's explicit bypass (app.bypass_tenant = 'on') sees everything — tooling only;
  * the ORM session publishes the context tenant automatically (core.database listener), so a
    session the code opens itself is scoped without any explicit set_config.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.tenant_context import system_scope, tenant_scope
from app.db.tenant_ddl import FAIL_CLOSED, SYSTEM_BYPASS

pytestmark = pytest.mark.asyncio

# A fresh NullPool engine per test: the app's shared pooled engine is bound to the first test's
# event loop, so reusing it across async tests fails with "Postgres not reachable".
engine = None


@pytest.fixture(autouse=True)
async def _engine():
    global engine
    url = get_settings().database_url
    if not url.startswith("postgresql"):
        pytest.skip("RLS is a Postgres feature; skipped on non-Postgres dialects")
    engine = create_async_engine(url, poolclass=NullPool)
    yield engine
    await engine.dispose()

_A = "00000000-0000-0000-0000-0000000000aa"
_B = "00000000-0000-0000-0000-0000000000bb"


async def _names(conn) -> list[str]:
    rows = (await conn.execute(text("SELECT name FROM mt_rls_test.student ORDER BY name"))).all()
    return [r[0] for r in rows]


async def _postgres_or_skip():
    if engine.dialect.name != "postgresql":
        pytest.skip("RLS is a Postgres feature; skipped on non-Postgres dialects")
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - environment-dependent
        pytest.skip("Postgres not reachable; RLS isolation test skipped")


async def _setup():
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS mt_rls_test CASCADE"))
        await conn.execute(text("CREATE SCHEMA mt_rls_test"))
        await conn.execute(text(
            "CREATE TABLE mt_rls_test.student (id serial primary key, name text, tenant_id uuid not null)"
        ))
        await conn.execute(text("ALTER TABLE mt_rls_test.student ENABLE ROW LEVEL SECURITY"))
        await conn.execute(text("ALTER TABLE mt_rls_test.student FORCE ROW LEVEL SECURITY"))
        await conn.execute(text(
            f"CREATE POLICY tenant_isolation ON mt_rls_test.student USING ({FAIL_CLOSED}) WITH CHECK ({FAIL_CLOSED})"
        ))
        await conn.execute(text(
            f"CREATE POLICY tenant_isolation_system ON mt_rls_test.student TO CURRENT_USER "
            f"USING ({SYSTEM_BYPASS}) WITH CHECK ({SYSTEM_BYPASS})"
        ))
    # Seed through the explicit bypass (as seeds and migrations do).
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.bypass_tenant', 'on', true)"))
        await conn.execute(text(
            "INSERT INTO mt_rls_test.student(name, tenant_id) VALUES "
            "('Alice-A', CAST(:a AS uuid)), ('Amir-A', CAST(:a AS uuid)), ('Bob-B', CAST(:b AS uuid))"
        ).bindparams(a=_A, b=_B))


async def _teardown():
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS mt_rls_test CASCADE"))


async def test_rls_is_fail_closed_and_isolates_tenants():
    await _postgres_or_skip()
    await _setup()
    try:
        async with engine.connect() as conn:
            # No tenant, no bypass → nothing (this used to return every tenant's rows).
            async with conn.begin():
                assert await _names(conn) == []
            # Tenant A sees only A.
            async with conn.begin():
                await conn.execute(text("SELECT set_config('app.current_tenant', :t, true)").bindparams(t=_A))
                assert await _names(conn) == ["Alice-A", "Amir-A"]
            # Next transaction on the same connection: the context did not leak.
            async with conn.begin():
                assert await _names(conn) == []
            # Tenant B sees only B.
            async with conn.begin():
                await conn.execute(text("SELECT set_config('app.current_tenant', :t, true)").bindparams(t=_B))
                assert await _names(conn) == ["Bob-B"]
            # The owner's explicit bypass sees everything (tooling only).
            async with conn.begin():
                await conn.execute(text("SELECT set_config('app.bypass_tenant', 'on', true)"))
                assert await _names(conn) == ["Alice-A", "Amir-A", "Bob-B"]

        # Writing without a tenant is refused.
        with pytest.raises(Exception):
            async with engine.begin() as conn:
                await conn.execute(text(
                    "INSERT INTO mt_rls_test.student(name, tenant_id) VALUES ('Nobody', CAST(:a AS uuid))"
                ).bindparams(a=_A))
        # Writing a row for another tenant is refused (WITH CHECK).
        with pytest.raises(Exception):
            async with engine.begin() as conn:
                await conn.execute(text("SELECT set_config('app.current_tenant', :t, true)").bindparams(t=_A))
                await conn.execute(text(
                    "INSERT INTO mt_rls_test.student(name, tenant_id) VALUES ('Sneaky', CAST(:b AS uuid))"
                ).bindparams(b=_B))
    finally:
        await _teardown()


async def test_orm_sessions_publish_the_context_tenant():
    """A session the code opens itself (e.g. a streaming AI feature) is scoped by the context
    tenant automatically, and sees nothing when there is none."""
    await _postgres_or_skip()
    await _setup()
    try:
        async def names() -> list[str]:
            async with AsyncSession(engine) as s:
                return [r[0] for r in (await s.execute(
                    text("SELECT name FROM mt_rls_test.student ORDER BY name"))).all()]

        assert await names() == []
        async with tenant_scope(uuid.UUID(_A)):
            assert await names() == ["Alice-A", "Amir-A"]
        async with tenant_scope(uuid.UUID(_B)):
            assert await names() == ["Bob-B"]
        async with system_scope():
            assert await names() == ["Alice-A", "Amir-A", "Bob-B"]
        assert await names() == []
    finally:
        await _teardown()
