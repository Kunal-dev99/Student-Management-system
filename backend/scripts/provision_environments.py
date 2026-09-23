"""Provision the prod / test / backup databases as EMPTY schema clones of dev (pgr).

Creates three sibling databases next to the current one and builds the full schema in each
by running the Alembic migrations to head — every table, foreign key, index and RLS policy,
with NO application data. (The migrations do insert the structural "default" tenant row, the
same as any fresh deployment — that is plumbing, not seed data.)

    python -m scripts.provision_environments            # create + build all three
    python -m scripts.provision_environments --only test

The current database (dev) is never touched. Requires the DB role to have CREATEDB — if it
does not, the script prints the one-line GRANT a superuser must run, and still builds the
schema for any target databases that already exist.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

import asyncpg

from app.core.config import get_settings

BACKEND = Path(__file__).resolve().parents[1]

# env name -> database name. Dev is the current DB and is left as-is.
TARGETS = {"prod": "pgr_prod", "test": "pgr_test", "backup": "pgr_backup"}


def _parts(url: str) -> dict:
    """Pull connection parts from the async SQLAlchemy DSN in settings."""
    m = re.match(r"^\w+\+\w+://([^:]+):([^@]*)@([^:/]+):(\d+)/(\w+)", url)
    if not m:
        sys.exit(f"Could not parse DATABASE_URL: {url}")
    user, pwd, host, port, db = m.groups()
    return {"user": user, "password": pwd, "host": host, "port": int(port), "db": db}


def _url_for(base_url: str, dbname: str) -> str:
    return re.sub(r"/(\w+)$", f"/{dbname}", base_url)


async def ensure_databases(p: dict, names: list[str]) -> list[str]:
    """CREATE DATABASE for each missing name (owner = the app role). Returns names that exist."""
    admin = await asyncpg.connect(user=p["user"], password=p["password"],
                                  host=p["host"], port=p["port"], database="postgres")
    can_create = await admin.fetchval(
        "SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname = current_user")
    present: list[str] = []
    for name in names:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", name)
        if exists:
            print(f"  {name}: already exists")
            present.append(name)
            continue
        if not can_create:
            print(f"  {name}: MISSING and current role cannot CREATE DATABASE")
            continue
        await admin.execute(f'CREATE DATABASE "{name}" OWNER "{p["user"]}"')
        print(f"  {name}: created")
        present.append(name)
    await admin.close()
    if not can_create:
        print("\n  A superuser must grant database creation once:")
        print(f"      ALTER ROLE {p['user']} CREATEDB;")
        print("  (or create the databases with deploy/create_environments.sql), then re-run.")
    return present


def build_schema(base_url: str, dbname: str) -> None:
    """Run `alembic upgrade head` against dbname in a subprocess with its own DATABASE_URL."""
    env = dict(os.environ)
    env["DATABASE_URL"] = _url_for(base_url, dbname)
    env.pop("APP_DATABASE_URL", None)  # build as the owner
    print(f"  {dbname}: building schema (alembic upgrade head)...")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                   cwd=str(BACKEND), env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


async def verify(p: dict, base_url: str, names: list[str]) -> None:
    async def counts(dbname: str) -> tuple[int, int, int]:
        c = await asyncpg.connect(user=p["user"], password=p["password"],
                                  host=p["host"], port=p["port"], database=dbname)
        tables = await c.fetchval("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")
        fks = await c.fetchval("SELECT count(*) FROM information_schema.table_constraints WHERE constraint_schema='public' AND constraint_type='FOREIGN KEY'")
        rls = await c.fetchval("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND rowsecurity=true")
        await c.close()
        return tables, fks, rls
    src = await counts(p["db"])
    print(f"\n  {'database':16s} {'tables':>7} {'fkeys':>7} {'rls':>5}")
    print(f"  {p['db']+' (dev, src)':16s} {src[0]:7d} {src[1]:7d} {src[2]:5d}")
    for name in names:
        t = await counts(name)
        ok = "OK" if t == src else "MISMATCH"
        print(f"  {name:16s} {t[0]:7d} {t[1]:7d} {t[2]:5d}  {ok}")


async def main_async(only: str | None) -> None:
    s = get_settings()
    base_url = s.database_url
    p = _parts(base_url)
    names = [TARGETS[only]] if only else list(TARGETS.values())
    print(f"Source (dev): {p['db']} on {p['host']}:{p['port']}\nProvisioning: {', '.join(names)}\n")
    present = await ensure_databases(p, names)
    for name in present:
        build_schema(base_url, name)
    if present:
        await verify(p, base_url, present)


def main() -> None:
    ap = argparse.ArgumentParser(description="Create prod/test/backup as empty schema clones of dev.")
    ap.add_argument("--only", choices=list(TARGETS), help="provision just one target")
    a = ap.parse_args()
    asyncio.run(main_async(a.only))


if __name__ == "__main__":
    main()
