"""Reusable DDL for the MT-4 tenancy fan-out.

MT-2 and MT-3 proved the pattern on the core spine (add nullable tenant_id + FK + index +
backfill, then ENABLE/FORCE RLS with one permissive-on-unset policy). Every subsequent
module repeats exactly that, so it lives here once and each module migration is just a
table list. This keeps 30 migrations identical and reviewable, and means a policy change
is a one-line edit in a single place.

Postgres-only by construction (RLS doesn't exist elsewhere) — but migrations only ever run
against the real Postgres DB; the SQLite test suite builds schema from the models, so it
never touches this. See tests/integration/test_tenant_rls_isolation.py for the guarantee.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"

# Isolate when a tenant is set; bypass when the context is absent (seeds/migrations/system).
# NULLIF(..., '') is essential: a custom GUC reverts to '' (not NULL) after a SET LOCAL on a
# pooled connection, and ''::uuid raises. NULLIF turns both unset and '' into NULL, so the
# ::uuid cast only ever sees a real uuid, and a NULL context means "bypass".
_PREDICATE = (
    "NULLIF(current_setting('app.current_tenant', true), '') IS NULL "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def add_tenant_columns(tables: tuple[str, ...] | list[str]) -> None:
    """Add nullable tenant_id + FK(RESTRICT) + index to each table and backfill to default."""
    for table in tables:
        op.add_column(table, sa.Column("tenant_id", sa.UUID(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_tenant_id", table, "tenant", ["tenant_id"], ["id"], ondelete="RESTRICT",
        )
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        op.execute(sa.text(
            f"UPDATE {table} SET tenant_id = CAST(:tid AS uuid) WHERE tenant_id IS NULL"
        ).bindparams(tid=DEFAULT_TENANT_ID))


def drop_tenant_columns(tables: tuple[str, ...] | list[str]) -> None:
    for table in reversed(list(tables)):
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_constraint(f"fk_{table}_tenant_id", table, type_="foreignkey")
        op.drop_column(table, "tenant_id")


def enable_rls(tables: tuple[str, ...] | list[str]) -> None:
    """ENABLE + FORCE RLS (app connects as owner) with the shared isolation policy."""
    for table in tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def disable_rls(tables: tuple[str, ...] | list[str]) -> None:
    for table in reversed(list(tables)):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def scope_tables(tables: tuple[str, ...] | list[str]) -> None:
    """Full upgrade for a module: columns + backfill, then RLS."""
    add_tenant_columns(tables)
    enable_rls(tables)


def unscope_tables(tables: tuple[str, ...] | list[str]) -> None:
    """Full downgrade for a module: RLS off, then drop columns."""
    disable_rls(tables)
    drop_tenant_columns(tables)
