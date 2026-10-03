"""Single-address SaaS: the narrow pre-sign-in lookups (migration t5_pre_auth_lookups).

They must answer "which institution?" for an email, user, referee token or bounced address,
leave the caller's transaction exactly as it was (no bypass left switched on), and be callable
only by the app - not by PUBLIC (e.g. a reporting login). Skipped unless the database is
Postgres and migrated to t5. Read-only.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

FUNCTIONS = ["pgr_tenant_of_email(text)", "pgr_tenant_of_user(uuid)",
             "pgr_tenant_of_reference(text)", "pgr_tenants_with_email(text)"]


@pytest_asyncio.fixture
async def engine():
    url = get_settings().database_url
    if not url.startswith("postgresql"):
        pytest.skip("Postgres only")
    eng = create_async_engine(url, poolclass=NullPool)
    try:
        async with eng.connect() as conn:
            present = await conn.scalar(text("SELECT to_regprocedure('pgr_tenant_of_email(text)')"))
    except Exception:
        await eng.dispose()
        pytest.skip("PostgreSQL not reachable")
    if present is None:
        await eng.dispose()
        pytest.skip("Database not migrated to t5_pre_auth_lookups yet")
    yield eng
    await eng.dispose()


async def test_lookups_find_the_institution_without_leaving_a_bypass(engine):
    async with engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SELECT set_config('app.bypass_tenant', 'on', true)"))
            user = (await conn.execute(text(
                "SELECT id, email, tenant_id FROM users WHERE email IS NOT NULL LIMIT 1"))).one()
        async with conn.begin():
            # A fresh transaction with no institution and no bypass: tables show nothing...
            assert await conn.scalar(text("SELECT count(*) FROM users")) == 0
            # ...but the lookups still answer, with institution ids only.
            assert await conn.scalar(text("SELECT pgr_tenant_of_email(:e)"), {"e": user.email.upper()}) == user.tenant_id
            assert await conn.scalar(text("SELECT pgr_tenant_of_user(:u)"), {"u": user.id}) == user.tenant_id
            many = [r[0] for r in await conn.execute(text("SELECT pgr_tenants_with_email(:e)"), {"e": user.email})]
            assert user.tenant_id in many
            assert await conn.scalar(text("SELECT pgr_tenant_of_email('nobody@nowhere.invalid')")) is None
            # The caller's transaction is exactly as it was: no bypass left on, still no rows.
            assert (await conn.scalar(text("SELECT coalesce(current_setting('app.bypass_tenant', true), '')"))) == ""
            assert await conn.scalar(text("SELECT count(*) FROM users")) == 0


async def test_lookups_are_not_callable_by_public(engine):
    async with engine.connect() as conn:
        for fn in FUNCTIONS:
            assert await conn.scalar(text("SELECT has_function_privilege('public', :f, 'EXECUTE')"), {"f": fn}) is False, fn
            definer = await conn.scalar(text("SELECT prosecdef FROM pg_proc WHERE oid = to_regprocedure(:f)"), {"f": fn})
            assert definer is True, fn
