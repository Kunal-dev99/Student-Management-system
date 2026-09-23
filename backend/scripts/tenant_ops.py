"""Per-tenant operations for the shared (pooled) database: stats / export / delete.

Because every tenant-owned row carries `tenant_id`, targeting one institution is precise.
This CLI does the three routine per-tenant jobs safely:

    python -m scripts.tenant_ops stats   <tenant>
    python -m scripts.tenant_ops export  <tenant> [--out DIR]
    python -m scripts.tenant_ops delete  <tenant> [--yes]

<tenant> is a tenant subdomain (e.g. "icr") or its uuid.

Safety:
* Runs as the DATABASE_URL role (the owner) so it can see and touch the tenant's rows, but
  every statement is explicitly scoped `WHERE tenant_id = <tenant>` — never a blind change.
* `export` is read-only. `delete` is a DRY RUN by default (prints what it *would* remove);
  it only commits with `--yes`, and the whole delete runs in ONE transaction, so any FK
  problem rolls the entire thing back — you never end up half-deleted.
* Deletes run children-first (topological FK order) and first clear the global rows that
  reference this tenant's users (auth tokens, role grants, statutory authorship).

Export writes one JSON-lines file per table plus a manifest.json (row counts + SHA-256 of
each file) — the input the "restore one tenant" runbook expects.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
from pathlib import Path

from sqlalchemy import text

from app.core.database import engine


def _json_default(o):
    if isinstance(o, (uuid.UUID,)):
        return str(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (bytes, memoryview)):
        return bytes(o).hex()
    return str(o)


async def _tenant_tables(conn) -> list[str]:
    rows = (await conn.execute(text(
        "SELECT table_name FROM information_schema.columns "
        "WHERE column_name='tenant_id' AND table_schema='public' ORDER BY table_name"
    ))).all()
    return [r[0] for r in rows]


async def _delete_order(conn, tables: list[str]) -> list[str]:
    """Topological order, children first: a table is deleted before any table it references."""
    tset = set(tables)
    edges = (await conn.execute(text(
        "SELECT tc.table_name AS child, ccu.table_name AS parent "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name "
        "JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name=ccu.constraint_name "
        "WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema='public'"
    ))).all()
    adj: dict[str, set[str]] = {t: set() for t in tables}
    indeg: dict[str, int] = {t: 0 for t in tables}
    for child, parent in edges:
        if child in tset and parent in tset and child != parent and parent not in adj[child]:
            adj[child].add(parent)
            indeg[parent] += 1
    queue = [t for t in tables if indeg[t] == 0]
    order: list[str] = []
    while queue:
        u = queue.pop()
        order.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    order += [t for t in tables if t not in order]  # any cycle leftovers (rare)
    return order


async def _resolve_tenant(conn, ident: str) -> tuple[uuid.UUID, str]:
    try:
        tid = uuid.UUID(ident)
        row = (await conn.execute(text("SELECT id, subdomain FROM tenant WHERE id=:i").bindparams(i=tid))).first()
    except ValueError:
        row = (await conn.execute(text("SELECT id, subdomain FROM tenant WHERE subdomain=:s").bindparams(s=ident.lower()))).first()
    if not row:
        sys.exit(f"No tenant matches {ident!r}. List them with: SELECT subdomain FROM tenant;")
    return row[0], row[1]


async def cmd_stats(ident: str) -> None:
    async with engine.connect() as conn:
        tid, sub = await _resolve_tenant(conn, ident)
        tables = await _tenant_tables(conn)
        print(f"tenant {sub} ({tid})")
        total = 0
        for t in tables:
            n = (await conn.execute(text(f'SELECT count(*) FROM "{t}" WHERE tenant_id=:i').bindparams(i=tid))).scalar()
            if n:
                print(f"  {t:34s} {n}")
                total += n
        print(f"  {'TOTAL':34s} {total}")


async def cmd_export(ident: str, out: str) -> None:
    async with engine.connect() as conn:
        tid, sub = await _resolve_tenant(conn, ident)
        tables = await _tenant_tables(conn)
        outdir = Path(out) / f"tenant_{sub}_{_utcnow():%Y%m%dT%H%M%SZ}"
        outdir.mkdir(parents=True, exist_ok=True)
        manifest = {"tenant_id": str(tid), "subdomain": sub,
                    "exported_at": _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "tables": {}}
        for t in tables:
            rows = (await conn.execute(text(f'SELECT * FROM "{t}" WHERE tenant_id=:i').bindparams(i=tid))).mappings().all()
            f = outdir / f"{t}.jsonl"
            with f.open("w", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps(dict(r), default=_json_default) + "\n")
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
            manifest["tables"][t] = {"rows": len(rows), "file": f.name, "sha256": digest}
            if rows:
                print(f"  {t:34s} {len(rows)}")
        (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        total = sum(v["rows"] for v in manifest["tables"].values())
        print(f"\nExported {total} rows across {len(tables)} tables -> {outdir}")


async def cmd_delete(ident: str, commit: bool) -> None:
    async with engine.begin() as conn:  # one transaction; rolls back unless we reach the end
        tid, sub = await _resolve_tenant(conn, ident)
        tables = await _tenant_tables(conn)
        order = await _delete_order(conn, tables)

        # Global rows that reference this tenant's users must be cleared first.
        user_ids_sql = "SELECT id FROM users WHERE tenant_id=:i"
        pre = [
            ("statutory_advisory.created_by",  f"UPDATE statutory_advisory SET created_by=NULL WHERE created_by IN ({user_ids_sql})"),
            ("statutory_advisory.decided_by",  f"UPDATE statutory_advisory SET decided_by=NULL WHERE decided_by IN ({user_ids_sql})"),
            ("statutory_spec_version.accepted_by", f"UPDATE statutory_spec_version SET accepted_by=NULL WHERE accepted_by IN ({user_ids_sql})"),
            ("refresh_token",       f"DELETE FROM refresh_token WHERE user_id IN ({user_ids_sql})"),
            ("password_reset_token", f"DELETE FROM password_reset_token WHERE user_id IN ({user_ids_sql})"),
            ("user_role",           f"DELETE FROM user_role WHERE user_id IN ({user_ids_sql})"),
        ]

        print(f"tenant {sub} ({tid}) — {'DELETING (will commit)' if commit else 'DRY RUN (nothing committed)'}\n")
        # Pre-clean global references.
        for label, sql in pre:
            res = await conn.execute(text(sql).bindparams(i=tid))
            if res.rowcount:
                print(f"  [global] {label:40s} {res.rowcount}")
        # Tenant tables, children first.
        total = 0
        for t in order:
            res = await conn.execute(text(f'DELETE FROM "{t}" WHERE tenant_id=:i').bindparams(i=tid))
            if res.rowcount:
                print(f"  {t:34s} {res.rowcount}")
                total += res.rowcount
        print(f"\n  {'TOTAL tenant rows':34s} {total}")

        if not commit:
            await conn.rollback()
            print("\nDRY RUN — rolled back. Re-run with --yes to delete for real.")
        else:
            print("\nCommitted. Tenant data removed.")


def main() -> None:
    p = argparse.ArgumentParser(description="Per-tenant stats / export / delete on the shared DB.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("stats", "export", "delete"):
        sp = sub.add_parser(name)
        sp.add_argument("tenant", help="tenant subdomain or uuid")
        if name == "export":
            sp.add_argument("--out", default="./var/tenant_exports", help="output directory")
        if name == "delete":
            sp.add_argument("--yes", action="store_true", help="actually commit the delete")
    a = p.parse_args()
    if a.cmd == "stats":
        asyncio.run(cmd_stats(a.tenant))
    elif a.cmd == "export":
        asyncio.run(cmd_export(a.tenant, a.out))
    elif a.cmd == "delete":
        asyncio.run(cmd_delete(a.tenant, commit=a.yes))


if __name__ == "__main__":
    main()
