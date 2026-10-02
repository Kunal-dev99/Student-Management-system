"""T2 — two-tenant sweep: call every GET endpoint as one institution and prove none of
another institution's records ever come back.

How it works (against the real, migrated Postgres database, read-only):

  1. Under the explicit bypass, snapshot every row id of every tenant table, and a few
     identifying values (emails, student numbers), grouped by tenant.
  2. Pick a viewer tenant. Mint a token for one of its users carrying EVERY permission, so
     permission checks never hide a leak — only tenant isolation stands in the way.
  3. Call every GET endpoint under /api/:
       * list endpoints as they are;
       * detail endpoints with ids that belong to OTHER tenants (and, as a control, with the
         viewer's own ids, which must work).
  4. Fail if any response contains another tenant's row id (other than the id we asked for)
     or another tenant's identifying values.

Run in both directions: the big default institution looking at a small one, and the reverse.
Skipped unless the database is Postgres, migrated to t1_tenant_hardening, and has data in at
least two tenants. Use ``python scripts/run_tenant_leak_tests.py`` to run it on a fresh copy.
"""
from __future__ import annotations

import re
import uuid
from collections import defaultdict

import pytest
import pytest_asyncio
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core import database
from app.core.config import get_settings
from app.core.security import create_access_token
from app.main import app

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# Values that identify a person or record, worth checking beyond ids.
_MARKER_COLUMNS = ("email", "student_number", "personal_email", "orcid", "hesa_id", "husid")
# Tried when a detail route's parameter doesn't name a table.
_CORE_TABLES = ("student", "person", "programme", "module", "application", "thesis",
                "supervision_arrangement", "funding_award", "milestone", "document")
# Endpoints that stream (SSE) are covered by the T1 smoke test, not here.
_SKIP = ("/stream",)


class Snapshot:
    def __init__(self) -> None:
        self.ids: dict[uuid.UUID, set[str]] = defaultdict(set)          # tenant -> ids
        self.by_table: dict[str, dict[uuid.UUID, list[str]]] = defaultdict(lambda: defaultdict(list))
        self.markers: dict[uuid.UUID, set[str]] = defaultdict(set)      # tenant -> values
        self.owner: dict[str, str] = {}                                 # id -> table

    def foreign_ids(self, viewer: uuid.UUID) -> set[str]:
        return set().union(*(v for t, v in self.ids.items() if t != viewer))

    def foreign_markers(self, viewer: uuid.UUID) -> set[str]:
        theirs = set().union(*(v for t, v in self.markers.items() if t != viewer))
        return theirs - self.markers[viewer]


async def _snapshot() -> Snapshot:
    snap = Snapshot()
    async with database.engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SELECT set_config('app.bypass_tenant', 'on', true)"))
            cols = defaultdict(set)
            for t, c in await conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public'"
            )):
                cols[t].add(c)
            for table, have in cols.items():
                if "tenant_id" not in have:
                    continue
                if "id" in have:
                    for rid, tid in await conn.execute(text(f'SELECT id::text, tenant_id FROM "{table}"')):
                        snap.ids[tid].add(rid)
                        snap.by_table[table][tid].append(rid)
                        snap.owner[rid] = table
                for col in _MARKER_COLUMNS:
                    if col in have:
                        for val, tid in await conn.execute(text(
                            f'SELECT "{col}"::text, tenant_id FROM "{table}" WHERE "{col}" IS NOT NULL'
                        )):
                            if len(val) >= 6:
                                snap.markers[tid].add(val.lower())
    return snap


async def _viewer_token(tid: uuid.UUID) -> str:
    async with database.engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SELECT set_config('app.bypass_tenant', 'on', true)"))
            user = (await conn.execute(text(
                "SELECT id, email FROM users WHERE tenant_id = :t ORDER BY created_at LIMIT 1"
            ).bindparams(t=tid))).first()
            perms = [r[0] for r in await conn.execute(text("SELECT code FROM permission"))]
            roles = [r[0] for r in await conn.execute(text("SELECT name FROM role"))]
    uid, email = (user[0], user[1]) if user else (uuid.uuid4(), "probe@leak.test")
    return create_access_token(str(uid), {
        "email": email, "personId": None, "roles": roles, "permissions": perms, "tenantId": str(tid),
    })


def _routes() -> list[APIRoute]:
    return sorted(
        (r for r in app.routes if isinstance(r, APIRoute) and "GET" in r.methods
         and r.path.startswith("/api/") and not any(s in r.path for s in _SKIP)),
        key=lambda r: r.path,
    )


def _guess_tables(path: str, param: str, tables: set[str]) -> list[str]:
    guesses = []
    if param.endswith("_id"):
        stem = param[:-3]
        guesses += [stem, stem.replace("supervisor_", "").replace("tutor", "person")]
    segs = [s for s in path.split("/") if s and not s.startswith("{")]
    before = path.split("{" + param + "}")[0].rstrip("/").split("/")[-1]
    for s in [before] + segs[::-1]:
        s = s.replace("-", "_")
        guesses += [s, s[:-1], s[:-2], s[:-3] + "y" if s.endswith("ies") else s]
    seen = []
    for g in guesses:
        if g in tables and g not in seen:
            seen.append(g)
    return seen[:2] or [t for t in _CORE_TABLES if t in tables]


def _fill(path: str, values: dict[str, str]) -> str:
    return re.sub(r"\{(\w+)(?::[^}]*)?\}", lambda m: values[m.group(1)], path)


async def _sweep(client: AsyncClient, snap: Snapshot, viewer: uuid.UUID) -> tuple[list, int, int]:
    headers = {"Authorization": f"Bearer {await _viewer_token(viewer)}"}
    foreign = snap.foreign_ids(viewer)
    markers = snap.foreign_markers(viewer)
    own = snap.ids[viewer]
    tables = set(snap.by_table)
    leaks: list[str] = []
    own_hits = own_detail_ok = 0

    def scan(url: str, body: str, asked: set[str]) -> None:
        nonlocal own_hits
        found = set(_UUID.findall(body.lower()))
        if found & own:
            own_hits += 1
        bad = (found & foreign) - asked
        if bad:
            sample = sorted(bad)[:3]
            leaks.append(f"{url}: {len(bad)} foreign id(s), e.g. "
                         + ", ".join(f"{i} ({snap.owner.get(i)})" for i in sample))
        low = body.lower()
        hit = [m for m in markers if m in low]
        if hit:
            leaks.append(f"{url}: foreign identifying values, e.g. {hit[:3]}")

    for route in _routes():
        params = re.findall(r"\{(\w+)", route.path)
        if not params:
            r = await client.get(route.path, headers=headers)
            if r.status_code < 400:
                scan(route.path, r.text, set())
            continue

        per_param = {p: _guess_tables(route.path, p, tables) for p in params}
        # Other tenants' ids: must be refused or come back empty.
        for i in range(3):
            values, asked = {}, set()
            for p, cands in per_param.items():
                pool = [rid for t in cands for tid, ids in snap.by_table[t].items() if tid != viewer
                        for rid in ids[:3]]
                values[p] = pool[i % len(pool)] if pool else str(uuid.uuid4())
                asked.add(values[p])
            url = _fill(route.path, values)
            r = await client.get(url, headers=headers)
            if r.status_code < 400:
                scan(url, r.text, asked)
        # Control: the viewer's own ids work, so a clean sweep isn't just "everything 404s".
        values = {}
        for p, cands in per_param.items():
            pool = [rid for t in cands for rid in snap.by_table[t].get(viewer, [])[:1]]
            values[p] = pool[0] if pool else str(uuid.uuid4())
        r = await client.get(_fill(route.path, values), headers=headers)
        if r.status_code == 200:
            own_detail_ok += 1
    return leaks, own_hits, own_detail_ok


@pytest_asyncio.fixture
async def client():
    if not get_settings().database_url.startswith("postgresql"):
        pytest.skip("Tenant isolation is enforced by Postgres; skipped on other dialects")
    # Pooled connections are bound to the event loop that opened them; start each test clean.
    for eng in {database.engine, database.read_engine, database.app_engine}:
        await eng.dispose()
    saved = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    try:
        async with database.engine.connect() as conn:
            hardened = await conn.scalar(text(
                "SELECT count(*) FROM pg_policies WHERE policyname = 'tenant_isolation_system'"))
    except Exception:
        pytest.skip("PostgreSQL not reachable")
    if not hardened:
        pytest.skip("Database not migrated to t1_tenant_hardening yet "
                    "(run scripts/run_tenant_leak_tests.py to test on a migrated copy)")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                               timeout=120) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)
        for eng in {database.engine, database.read_engine, database.app_engine}:
            await eng.dispose()


@pytest.mark.parametrize("direction", ["largest_views_others", "smaller_views_largest"])
async def test_no_endpoint_returns_another_tenants_records(client, direction):
    snap = await _snapshot()
    tenants = sorted((t for t in snap.ids if snap.ids[t]), key=lambda t: -len(snap.ids[t]))
    if len(tenants) < 2:
        pytest.skip("Needs data in at least two tenants")
    viewer = tenants[0] if direction == "largest_views_others" else tenants[1]

    leaks, own_hits, own_detail_ok = await _sweep(client, snap, viewer)

    assert leaks == [], f"{len(leaks)} cross-tenant leak(s):\n  " + "\n  ".join(leaks[:40])
    # Non-vacuous: the viewer really did see its own data through the API.
    if direction == "largest_views_others":
        assert own_hits >= 20, f"only {own_hits} responses contained the viewer's own records"
        assert own_detail_ok >= 10, f"only {own_detail_ok} detail endpoints worked for own records"
    else:
        assert own_hits >= 1
