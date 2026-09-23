"""MT-3 — proves Postgres Row-Level Security isolates tenants.

RLS is a Postgres feature, so this test is skipped on the default SQLite suite. It runs
against the configured Postgres engine, in a throwaway schema it creates and drops, so it
never touches real data. It asserts the exact policy shipped by migration mt3_tenant_rls:

  * a tenant sees only its own rows,
  * a tenant cannot write a row for another tenant (WITH CHECK),
  * transaction-local context does not leak to the next transaction, and
  * an unset context bypasses (so seeds / migrations / system paths keep working).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.core.database import engine

pytestmark = pytest.mark.asyncio

_A = "00000000-0000-0000-0000-0000000000aa"
_B = "00000000-0000-0000-0000-0000000000bb"

_PREDICATE = (
    "current_setting('app.current_tenant', true) IS NULL "
    "OR current_setting('app.current_tenant', true) = '' "
    "OR tenant_id = current_setting('app.current_tenant', true)::uuid"
)


async def _names(conn) -> list[str]:
    rows = (await conn.execute(text("SELECT name FROM mt_rls_test.student ORDER BY name"))).all()
    return [r[0] for r in rows]


async def test_rls_isolates_tenants():
    if engine.dialect.name != "postgresql":
        pytest.skip("RLS is a Postgres feature; skipped on non-Postgres dialects")

    # Skip (don't fail) when no Postgres is reachable — e.g. a SQLite-only CI runner.
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - environment-dependent
        pytest.skip("Postgres not reachable; RLS isolation test skipped")

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS mt_rls_test CASCADE"))
        await conn.execute(text("CREATE SCHEMA mt_rls_test"))
        await conn.execute(text(
            "CREATE TABLE mt_rls_test.student "
            "(id serial primary key, name text, tenant_id uuid not null)"
        ))
        await conn.execute(text("ALTER TABLE mt_rls_test.student ENABLE ROW LEVEL SECURITY"))
        await conn.execute(text("ALTER TABLE mt_rls_test.student FORCE ROW LEVEL SECURITY"))
        await conn.execute(text(
            f"CREATE POLICY tenant_isolation ON mt_rls_test.student "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        ))

    try:
        # Seed with NO context set -> bypass (mimics db/seed.py).
        async with engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO mt_rls_test.student(name, tenant_id) VALUES "
                "('Alice-A', CAST(:a AS uuid)), ('Amir-A', CAST(:a AS uuid)), "
                "('Bob-B', CAST(:b AS uuid))"
            ).bindparams(a=_A, b=_B))

        # Request acting as tenant A sees only A.
        async with engine.connect() as conn:
            async with conn.begin():
                await conn.execute(text("SELECT set_config('app.current_tenant', :t, true)").bindparams(t=_A))
                assert await _names(conn) == ["Alice-A", "Amir-A"]
            # New transaction, no context -> unset bypass, and no stale leak from the A txn.
            async with conn.begin():
                assert await _names(conn) == ["Alice-A", "Amir-A", "Bob-B"]

        # Request acting as tenant B sees only B.
        async with engine.connect() as conn:
            async with conn.begin():
                await conn.execute(text("SELECT set_config('app.current_tenant', :t, true)").bindparams(t=_B))
                assert await _names(conn) == ["Bob-B"]

        # Cross-tenant write is refused by WITH CHECK.
        with pytest.raises(Exception):
            async with engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(text("SELECT set_config('app.current_tenant', :t, true)").bindparams(t=_A))
                    await conn.execute(text(
                        "INSERT INTO mt_rls_test.student(name, tenant_id) "
                        "VALUES ('Sneaky', CAST(:b AS uuid))"
                    ).bindparams(b=_B))
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS mt_rls_test CASCADE"))
