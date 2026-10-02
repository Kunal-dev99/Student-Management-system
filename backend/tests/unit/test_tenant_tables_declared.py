"""T2 — every model is either tenant-owned or deliberately global.

Runs without a database, so it guards every build: a new model that forgets TenantMixin fails
here unless someone adds it to GLOBAL_TABLES with a reason (which is the review point).
The Postgres side of the same rule is tests/integration/test_tenant_guard.py.
"""
from __future__ import annotations

import app.main  # noqa: F401  (registers every model on Base.metadata)
from app.db.base import Base
from app.db.tenant_guard import GLOBAL_TABLES


def test_every_table_is_tenant_owned_or_listed_as_global():
    undeclared = sorted(
        t.name for t in Base.metadata.sorted_tables
        if "tenant_id" not in t.c and t.name not in GLOBAL_TABLES
    )
    assert undeclared == [], (
        f"Tables with no tenant_id: {undeclared}. Add TenantMixin, or list them in "
        "app/db/tenant_guard.GLOBAL_TABLES with the reason they are safe to share."
    )


def test_global_list_has_no_stale_entries():
    tables = set(Base.metadata.tables)
    assert sorted(set(GLOBAL_TABLES) - tables) == []
    # A global table that grows a tenant column should come off the list.
    assert sorted(n for n in GLOBAL_TABLES if "tenant_id" in Base.metadata.tables[n].c) == []


def test_tenant_column_is_compulsory_and_stamped():
    loose = []
    for t in Base.metadata.sorted_tables:
        col = t.c.get("tenant_id")
        if col is None:
            continue
        if col.nullable or col.default is None:
            loose.append(t.name)
    assert loose == [], f"tenant_id must be NOT NULL with a tenant-stamping default: {loose}"
