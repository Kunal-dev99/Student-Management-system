"""Per-institution reporting access (T3): view schemas and read-only reporting logins.

    python -m scripts.tenant_reporting status
    python -m scripts.tenant_reporting rebuild [<tenant>]
    python -m scripts.tenant_reporting create-login <tenant> [--full]
    python -m scripts.tenant_reporting rotate       <tenant> [--full]
    python -m scripts.tenant_reporting drop-login   <tenant> [--full]

<tenant> is a subdomain (e.g. "icr") or a tenant uuid.

Each institution gets two schemas of views (see app/db/tenant_views.py): ``tenant_<sub>``
(standard, no personal data) and ``tenant_<sub>_full``. A reporting login is a Postgres role:

  <sub>_reporting        reads tenant_<sub> only
  <sub>_reporting_full   reads both (only when the institution asks for personal data)

Both are read-only, pinned to their institution, have no privileges on the core tables, a
connection limit and a statement timeout. The password is printed ONCE — put it straight into
the institution's secret store; it is never written anywhere by this tool.

Creating logins needs the one-time superuser step in deploy/provision_reporting.sql (the
owner role can't create roles, or pin a tenant on them, without it).
"""
from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
import uuid

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine
from app.db import tenant_views

CONNECTION_LIMIT = 5
STATEMENT_TIMEOUT = "120s"


async def _resolve(conn, ident: str) -> tuple[uuid.UUID, str]:
    try:
        row = (await conn.execute(text("SELECT id, subdomain FROM tenant WHERE id = :i"),
                                  {"i": uuid.UUID(ident)})).first()
    except ValueError:
        row = (await conn.execute(text("SELECT id, subdomain FROM tenant WHERE subdomain = :s"),
                                  {"s": ident.lower()})).first()
    if not row:
        sys.exit(f"No tenant matches {ident!r}.")
    return row[0], row[1]


async def _can_manage_roles(conn) -> bool:
    return bool(await conn.scalar(text(
        "SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user")))


async def cmd_status() -> None:
    async with engine.connect() as conn:
        owner = await conn.run_sync(tenant_views.view_owner)
        manage = await _can_manage_roles(conn)
        print(f"view owner: {owner}"
              + ("" if owner == tenant_views.VIEW_OWNER else
                 "  (not provisioned: views run as the table owner; run deploy/provision_reporting.sql)"))
        print(f"can create reporting logins: {'yes' if manage else 'no (needs deploy/provision_reporting.sql)'}\n")
        tenants = (await conn.execute(text(
            "SELECT id, subdomain, deactivated_at FROM tenant ORDER BY subdomain"))).all()
        for tid, sub, off in tenants:
            std, full = tenant_views.schemas(sub)
            views = await conn.scalar(text(
                "SELECT count(*) FROM pg_views WHERE schemaname = :s"), {"s": std})
            roles = [r[0] for r in await conn.execute(text(
                "SELECT rolname FROM pg_roles WHERE rolname IN (:a, :b) ORDER BY 1"),
                dict(zip("ab", tenant_views.reporting_roles(sub))))]
            state = "deactivated" if off else "active"
            print(f"  {sub:12s} {state:11s} {std}: {views} views   logins: {', '.join(roles) or '-'}")


async def cmd_rebuild(ident: str | None) -> None:
    async with engine.begin() as conn:
        only = (await _resolve(conn, ident))[0] if ident else None
        built = await conn.run_sync(tenant_views.rebuild, only)
    for sub, n in built.items():
        print(f"  {sub}: {n} views in each of {', '.join(tenant_views.schemas(sub))}")


def _dsn(role: str, password: str) -> str:
    url = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
    host_db = url.split("@", 1)[-1]
    return f"postgresql://{role}:{password}@{host_db}"


async def cmd_create(ident: str, full: bool, rotate: bool = False) -> None:
    async with engine.begin() as conn:
        if not await _can_manage_roles(conn):
            sys.exit("This database login can't create roles. Run deploy/provision_reporting.sql "
                     "as a superuser once, then try again.")
        tid, sub = await _resolve(conn, ident)
        role = tenant_views.reporting_roles(sub)[1 if full else 0]
        std, full_schema = tenant_views.schemas(sub)
        db = await conn.scalar(text("SELECT current_database()"))
        exists = await conn.scalar(text("SELECT count(*) FROM pg_roles WHERE rolname = :r"), {"r": role})
        if rotate and not exists:
            sys.exit(f"{role} doesn't exist; create it first.")
        if not rotate and exists:
            sys.exit(f"{role} already exists; use rotate to issue a new password.")

        password = secrets.token_urlsafe(32)   # [A-Za-z0-9_-] only, safe as a literal
        q = tenant_views._q
        if rotate:
            await conn.execute(text(f"ALTER ROLE {q(role)} PASSWORD '{password}'"))
        else:
            await conn.execute(text(
                f"CREATE ROLE {q(role)} LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE "
                f"NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT {CONNECTION_LIMIT}"))
            settings = {
                # Pins the login to its institution for row-level security (lock 1). The views'
                # fixed filter (lock 2) holds even if the login changes this in its session.
                "app.current_tenant": str(tid),
                "default_transaction_read_only": "on",
                "statement_timeout": STATEMENT_TIMEOUT,
                "search_path": full_schema if full else std,
            }
            for key, value in settings.items():
                await conn.execute(text(
                    f"ALTER ROLE {q(role)} IN DATABASE {q(db)} SET {key} = '{value}'"))
            await conn.execute(text(f"GRANT CONNECT ON DATABASE {q(db)} TO {q(role)}"))
            await conn.run_sync(tenant_views.rebuild, tid)   # applies the schema grants

    print(f"{'Rotated' if rotate else 'Created'} {role} ({'full detail' if full else 'standard'} views, "
          f"read-only, pinned to {sub}).")
    print("Password (shown once; store it in the institution's secret store now):")
    print(f"  {password}")
    print(f"Connection string: {_dsn(role, password)}")


async def cmd_drop(ident: str, full: bool) -> None:
    async with engine.begin() as conn:
        if not await _can_manage_roles(conn):
            sys.exit("This database login can't drop roles (see deploy/provision_reporting.sql).")
        tid, sub = await _resolve(conn, ident)
        role = tenant_views.reporting_roles(sub)[1 if full else 0]
        db = await conn.scalar(text("SELECT current_database()"))
        if not await conn.scalar(text("SELECT count(*) FROM pg_roles WHERE rolname = :r"), {"r": role}):
            sys.exit(f"{role} doesn't exist.")
        q = tenant_views._q
        # Its only privileges are on this institution's views and the database: drop the views
        # (taking those grants with them), revoke CONNECT, drop the role, then rebuild the views.
        for schema in tenant_views.schemas(sub):
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {q(schema)} CASCADE"))
        await conn.execute(text(f"REVOKE ALL ON DATABASE {q(db)} FROM {q(role)}"))
        await conn.execute(text(f"ALTER ROLE {q(role)} IN DATABASE {q(db)} RESET ALL"))
        await conn.execute(text(f"DROP ROLE {q(role)}"))
        await conn.run_sync(tenant_views.rebuild, tid)
    print(f"Dropped {role}.")


def main() -> None:
    p = argparse.ArgumentParser(description="Per-institution reporting views and logins.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sp = sub.add_parser("rebuild")
    sp.add_argument("tenant", nargs="?", help="subdomain or uuid (default: all)")
    for name in ("create-login", "rotate", "drop-login"):
        sp = sub.add_parser(name)
        sp.add_argument("tenant", help="subdomain or uuid")
        sp.add_argument("--full", action="store_true", help="the full-detail (personal data) login")
    a = p.parse_args()
    if a.cmd == "status":
        asyncio.run(cmd_status())
    elif a.cmd == "rebuild":
        asyncio.run(cmd_rebuild(a.tenant))
    elif a.cmd == "create-login":
        asyncio.run(cmd_create(a.tenant, a.full))
    elif a.cmd == "rotate":
        asyncio.run(cmd_create(a.tenant, a.full, rotate=True))
    elif a.cmd == "drop-login":
        asyncio.run(cmd_drop(a.tenant, a.full))


if __name__ == "__main__":
    main()
