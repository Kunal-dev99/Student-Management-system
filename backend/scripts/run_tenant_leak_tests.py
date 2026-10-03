"""Run the tenant isolation tests (T2 leak tests, T3 views) on a throwaway, fully migrated copy of the database.

    python scripts/run_tenant_leak_tests.py            # copy of the DATABASE_URL database
    python scripts/run_tenant_leak_tests.py --keep     # leave the copy for inspection

The leak tests need the database at the latest migration (t1_tenant_hardening or later) and
real data in at least two tenants. Rather than migrating your working database, this copies
it (CREATE DATABASE ... TEMPLATE), migrates the copy to head, runs the tests against it, and
drops it. Your database is only read, never changed.

Postgres refuses to copy a database while other sessions are connected to it, so stop the
API (and any psql sessions) first. Exit code is pytest's.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import asyncpg
from dotenv import dotenv_values

BACKEND = Path(__file__).resolve().parents[1]
TESTS = [
    "tests/unit/test_tenant_tables_declared.py",
    "tests/integration/test_tenant_rls_isolation.py",
    "tests/integration/test_tenant_guard.py",
    "tests/integration/test_tenant_leak_api.py",
    "tests/unit/test_tenant_view_catalogue.py",
    "tests/integration/test_tenant_views.py",
    "tests/integration/test_pre_auth_lookups.py",
    "tests/integration/test_warehouse_tracking.py",
]


def _urls() -> tuple[str, str, str]:
    url = os.environ.get("DATABASE_URL") or dotenv_values(BACKEND / ".env").get("DATABASE_URL") or ""
    if not url.startswith("postgres"):
        sys.exit("DATABASE_URL must point at Postgres")
    raw = url.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")
    base, source = raw.rsplit("/", 1)
    return base, source.split("?")[0], f"{source.split('?')[0]}_leak_test"


async def _admin(base: str, sql: str) -> None:
    conn = await asyncpg.connect(base + "/postgres")
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def main() -> int:
    keep = "--keep" in sys.argv
    base, source, copy = _urls()
    print(f"Copying {source} -> {copy} ...")
    asyncio.run(_admin(base, f'DROP DATABASE IF EXISTS "{copy}" WITH (FORCE)'))
    try:
        asyncio.run(_admin(base, f'CREATE DATABASE "{copy}" TEMPLATE "{source}"'))
    except asyncpg.ObjectInUseError:
        sys.exit(f"{source} has other sessions connected; stop the API and try again.")

    env = dict(os.environ,
               DATABASE_URL=base.replace("postgresql://", "postgresql+asyncpg://") + "/" + copy,
               DATABASE_REPLICA_URL="", APP_DATABASE_URL="")
    env.pop("DATABASE_REPLICA_URL")
    env.pop("APP_DATABASE_URL")
    try:
        print("Migrating the copy to head ...")
        mig = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env)
        if mig.returncode:
            return mig.returncode
        print("Running the tenant-leak tests ...")
        return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:logging", *TESTS],
                              cwd=BACKEND, env=env).returncode
    finally:
        if keep:
            print(f"Kept {copy}.")
        else:
            asyncio.run(_admin(base, f'DROP DATABASE IF EXISTS "{copy}" WITH (FORCE)'))
            print(f"Dropped {copy}.")


if __name__ == "__main__":
    sys.exit(main())
