"""T1 — tenant isolation hardening: fail-closed RLS everywhere, tenant_id compulsory.

Before: every RLS table had one PUBLIC policy that let everything through when no tenant was
set ("bypass when unset"), so a code path that forgot the tenant saw every institution's rows.
The MT-6 fail-closed policy for pgr_app was only ever installed on the tables that existed when
it ran, and pgr_app was never provisioned here. composer_run had no policy at all.

After, on every table with a tenant_id column:
  * RLS enabled and forced;
  * tenant_isolation (PUBLIC)  — tenant_id = the acting tenant, nothing else (fail-closed);
  * tenant_isolation_system (owner only) — explicit opt-in bypass (app.bypass_tenant = 'on'),
    used by migrations, seeds and the worker's tenant loop via system_scope();
  * tenant_id NOT NULL. The migration refuses to run if any row has no tenant.

Revision ID: t1_tenant_hardening
Revises: ed12_engagement
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.tenant_ddl import FAIL_CLOSED, apply_policies

revision: str = "t1_tenant_hardening"
down_revision: Union[str, Sequence[str], None] = "ed12_engagement"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.t1")

_OLD_PERMISSIVE = (
    "NULLIF(current_setting('app.current_tenant', true), '') IS NULL "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)


def _tenant_tables(bind) -> list[str]:
    return [r[0] for r in bind.execute(sa.text("""
        SELECT c.table_name FROM information_schema.columns c
        JOIN pg_class cl ON cl.relname = c.table_name AND cl.relkind = 'r'
        JOIN pg_namespace n ON n.oid = cl.relnamespace AND n.nspname = 'public'
        WHERE c.table_schema = 'public' AND c.column_name = 'tenant_id'
        ORDER BY c.table_name
    """))]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    tables = _tenant_tables(bind)

    # 1) No row may be left without a tenant (they would vanish under fail-closed RLS).
    empty = {}
    for t in tables:
        n = bind.execute(sa.text(f'SELECT count(*) FROM "{t}" WHERE tenant_id IS NULL')).scalar()
        if n:
            empty[t] = n
    if empty:
        raise RuntimeError(f"Rows without a tenant — assign them before hardening: {empty}")

    # 2) RLS forced + the fail-closed policy pair on every tenant table (composer_run included).
    for t in tables:
        op.execute(f'ALTER TABLE "{t}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{t}" FORCE ROW LEVEL SECURITY')
        apply_policies(t)

    # 3) tenant_id is compulsory.
    for t in tables:
        op.execute(f'ALTER TABLE "{t}" ALTER COLUMN tenant_id SET NOT NULL')

    log.info("T1 hardening: %s tenant tables now fail-closed with tenant_id NOT NULL", len(tables))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for t in _tenant_tables(bind):
        op.execute(f'ALTER TABLE "{t}" ALTER COLUMN tenant_id DROP NOT NULL')
        for name in ("tenant_isolation", "tenant_isolation_system", "tenant_isolation_app"):
            op.execute(f'DROP POLICY IF EXISTS {name} ON "{t}"')
        if t == "composer_run":
            op.execute(f'ALTER TABLE "{t}" NO FORCE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{t}" DISABLE ROW LEVEL SECURITY')
            continue
        # Back to the pre-T1 single PUBLIC "bypass when unset" policy.
        op.execute(f'CREATE POLICY tenant_isolation ON "{t}" USING ({_OLD_PERMISSIVE}) WITH CHECK ({_OLD_PERMISSIVE})')


_ = FAIL_CLOSED  # documented in tenant_ddl; imported so the predicate has one source
