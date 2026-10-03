"""T3 — the per-institution view layer, on the real migrated Postgres database.

Always (once migrated):
  * every active institution has its standard and full-detail schemas with every published view;
  * each view returns exactly that institution's rows;
  * the fixed filter holds on its own: pointed at another institution, or with the owner's
    bypass switched on, a view still never returns another institution's rows;
  * the standard schema carries no personal data; the full one does;
  * a rebuild after dropping everything (what every migration does) restores the same views.

Once deploy/provision_reporting.sql has been run (otherwise skipped), with a real reporting
login created and dropped through scripts/tenant_reporting.py:
  * it reads its own views and nothing else: core tables and other institutions' schemas are
    refused, and so are writes;
  * changing its own tenant setting, or switching on the bypass, never shows another
    institution's rows.

Read-only apart from the throwaway login. Run on a migrated copy with
``python scripts/run_tenant_leak_tests.py``.
"""
from __future__ import annotations

import re
import uuid

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db import tenant_views
from app.db.tenant_views import CATALOGUE, schemas


@pytest_asyncio.fixture
async def engine():
    url = get_settings().database_url
    if not url.startswith("postgresql"):
        pytest.skip("Postgres only")
    eng = create_async_engine(url, poolclass=NullPool)
    try:
        async with eng.connect() as conn:
            built = await conn.scalar(text(
                "SELECT count(*) FROM pg_namespace WHERE obj_description(oid, 'pg_namespace') = 'pgr tenant views'"))
    except Exception:
        await eng.dispose()
        pytest.skip("PostgreSQL not reachable")
    if not built:
        await eng.dispose()
        pytest.skip("No tenant view schemas yet (migrate to head, or run scripts/run_tenant_leak_tests.py)")
    yield eng
    await eng.dispose()


async def _tenants(conn) -> list[tuple[uuid.UUID, str]]:
    return [(r[0], r[1]) for r in await conn.execute(text(
        "SELECT id, subdomain FROM tenant WHERE deactivated_at IS NULL ORDER BY subdomain"))]


async def _published(conn) -> list:
    tables = {r[0] for r in await conn.execute(text(
        "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' AND column_name = 'tenant_id'"))}
    return [o for o in CATALOGUE if o.table in tables]


async def _count(conn, sql: str, tenant: str = "", bypass: bool = False) -> int:
    async with conn.begin():
        await conn.execute(text(
            "SELECT set_config('app.current_tenant', :t, true), set_config('app.bypass_tenant', :b, true)"
        ).bindparams(t=tenant, b="on" if bypass else ""))
        return await conn.scalar(text(sql))


async def test_every_institution_has_every_view(engine):
    async with engine.connect() as conn:
        tenants = await _tenants(conn)
        published = {o.name for o in await _published(conn)}
        views = {(r[0], r[1]) for r in await conn.execute(text("SELECT schemaname, viewname FROM pg_views"))}
        barrier = {r[0] for r in await conn.execute(text(
            "SELECT n.nspname || '.' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relkind = 'v' AND 'security_barrier=true' = ANY(c.reloptions)"))}
        await conn.rollback()
    assert len(tenants) >= 2 and len(published) >= 20
    for _, sub in tenants:
        for schema in schemas(sub):
            have = {v for s, v in views if s == schema}
            assert have == published, f"{schema}: missing {sorted(published - have)}"
            assert {f"{schema}.{v}" for v in have} <= barrier, f"{schema}: views must be security_barrier"


async def test_views_return_exactly_their_own_institution(engine):
    async with engine.connect() as conn:
        tenants = await _tenants(conn)
        published = await _published(conn)
        # Provisioned, the views run as pgr_views, which is not the table owner, so the owner's
        # bypass gives it nothing. Unprovisioned (dev), they run as the owner and the bypass
        # lets RLS through, leaving the fixed filter as the lock.
        provisioned = await conn.run_sync(tenant_views.view_owner) == tenant_views.VIEW_OWNER
        await conn.rollback()
        nonempty = 0
        for tid, sub in tenants:
            std, full = schemas(sub)
            other = next(str(t) for t, _ in tenants if t != tid)
            for obj in published:
                own = await _count(conn, f'SELECT count(*) FROM public."{obj.table}" WHERE tenant_id = \'{tid}\'',
                                   bypass=True)
                nonempty += bool(own)
                for schema in (std, full):
                    view = f'"{schema}"."{obj.name}"'
                    assert await _count(conn, f"SELECT count(*) FROM {view}", tenant=str(tid)) == own, view
                    # Lock 2 on its own: pointed at another institution, or with the bypass, the
                    # fixed filter still returns only this institution's rows.
                    assert await _count(conn, f"SELECT count(*) FROM {view}", tenant=other) == 0, view
                    expected = 0 if provisioned else own
                    assert await _count(conn, f"SELECT count(*) FROM {view}", bypass=True) == expected, view
        assert nonempty >= 20, "too little data for this test to mean anything"


async def test_standard_views_have_no_personal_data(engine):
    async with engine.connect() as conn:
        tenants = await _tenants(conn)
        published = await _published(conn)
        cols: dict[tuple[str, str], set[str]] = {}
        for s, t, c in await conn.execute(text(
            "SELECT table_schema, table_name, column_name FROM information_schema.columns "
            "WHERE table_schema LIKE 'tenant\\_%'")):
            cols.setdefault((s, t), set()).add(c)
        await conn.rollback()
    for _, sub in tenants:
        std, full = schemas(sub)
        for obj in published:
            leaked = set(obj.personal) & cols[(std, obj.name)]
            assert leaked == set(), f"{std}.{obj.name} exposes {leaked}"
            assert set(obj.personal) <= cols[(full, obj.name)] | set()
        assert "birth_year" in cols[(std, "person")]
        assert "date_of_birth" not in cols[(std, "person")]
        assert {"given_name", "family_name", "email", "date_of_birth"} <= cols[(full, "person")]


async def test_rebuild_after_drop_restores_the_views(engine):
    """What every migration does: drop all view schemas, migrate, rebuild."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            before = sorted(tuple(r) for r in await conn.execute(text(
                "SELECT schemaname, viewname FROM pg_views WHERE schemaname LIKE 'tenant\\_%'")))
            dropped = await conn.run_sync(tenant_views.drop_all)
            assert dropped >= 4
            assert not await conn.scalar(text("SELECT count(*) FROM pg_views WHERE schemaname LIKE 'tenant\\_%'"))
            await conn.run_sync(tenant_views.rebuild)
            after = sorted(tuple(r) for r in await conn.execute(text(
                "SELECT schemaname, viewname FROM pg_views WHERE schemaname LIKE 'tenant\\_%'")))
        finally:
            await trans.rollback()
    assert after == before


# --------------------------------------------------------------------------------------------
# A real reporting login (needs deploy/provision_reporting.sql)
# --------------------------------------------------------------------------------------------

def _plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def test_reporting_login_sees_only_its_own_views(engine, capsys):
    async with engine.connect() as conn:
        can = await conn.scalar(text(
            "SELECT (rolsuper OR rolcreaterole) AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgr_views') "
            "FROM pg_roles WHERE rolname = current_user"))
        tenants = await _tenants(conn)
        await conn.rollback()
    if not can:
        pytest.skip("Reporting not provisioned (run deploy/provision_reporting.sql as a superuser)")

    from app.core import database
    from scripts import tenant_reporting

    # Pick the institution with the most students, and one other.
    async with engine.connect() as conn:
        counts = {sub: await _count(conn, f"SELECT count(*) FROM student WHERE tenant_id = '{tid}'", bypass=True)
                  for tid, sub in tenants}
    sub = max(counts, key=counts.get)
    tid = next(t for t, s in tenants if s == sub)
    other_sub = next(s for _, s in tenants if s != sub)
    other_tid = next(t for t, s in tenants if s == other_sub)
    role = tenant_views.reporting_roles(sub)[0]
    std, full = schemas(sub)

    await database.engine.dispose()   # the script uses the app engine; bind it to this loop
    await tenant_reporting.cmd_create(sub, full=False)
    password = re.search(r"Password.*\n\s+(\S+)", capsys.readouterr().out).group(1)
    host_db = _plain(get_settings().database_url).split("@", 1)[1]
    try:
        login = await asyncpg.connect(f"postgresql://{role}:{password}@{host_db}")
        try:
            # Its own standard views work, and are pinned to its institution.
            assert await login.fetchval(f'SELECT count(*) FROM "{std}".student') == counts[sub]
            assert await login.fetchval("SELECT current_setting('app.current_tenant')") == str(tid)
            # Core tables, the full-detail schema and other institutions' schemas: refused.
            for sql in ("SELECT count(*) FROM public.student", "SELECT count(*) FROM public.users",
                        f'SELECT count(*) FROM "{full}".person',
                        f'SELECT count(*) FROM "{schemas(other_sub)[0]}".student'):
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    await login.fetchval(sql)
            # Writes: refused.
            with pytest.raises(asyncpg.PostgresError):
                await login.execute(f'DELETE FROM "{std}".student')
            # Changing its own tenant setting shows nothing: RLS now allows the other
            # institution, but the view's fixed filter allows only its own. The owner's bypass
            # does nothing for it (it isn't the table owner).
            await login.execute(f"SET app.current_tenant = '{other_tid}'")
            assert await login.fetchval(f'SELECT count(*) FROM "{std}".student') == 0
            await login.execute("SET app.bypass_tenant = 'on'")
            assert await login.fetchval(f'SELECT count(*) FROM "{std}".student') == 0
            await login.execute("RESET app.bypass_tenant")
            await login.execute("RESET app.current_tenant")   # back to the pinned institution
            ids = {r[0] for r in await login.fetch(f'SELECT id FROM "{std}".student')}
        finally:
            await login.close()
        async with engine.connect() as conn, conn.begin():
            await conn.execute(text("SELECT set_config('app.bypass_tenant', 'on', true)"))
            own = {r[0] for r in await conn.execute(text(
                "SELECT id FROM student WHERE tenant_id = :t").bindparams(t=tid))}
        assert ids == own
    finally:
        await database.engine.dispose()
        await tenant_reporting.cmd_drop(sub, full=False)
        await database.engine.dispose()
    async with engine.connect() as conn:
        assert not await conn.scalar(text("SELECT count(*) FROM pg_roles WHERE rolname = :r"), {"r": role})
