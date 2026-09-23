"""MT-4 (25) — fix the RLS policy predicate to guard the uuid cast.

The MT-2/MT-3/MT-4 policies cast current_setting('app.current_tenant')::uuid with a plain
`= ''` bypass term. On a POOLED connection a custom GUC reverts to '' (not NULL) after a
SET LOCAL transaction, and Postgres does not guarantee OR short-circuits around the cast,
so a later query on that connection hit `invalid input syntax for type uuid: ""`.

This recreates the `tenant_isolation` policy on every RLS-enabled table using
NULLIF(current_setting(...), '') so the ::uuid cast only ever sees a real uuid, and both
unset and '' mean "bypass". Idempotent and data-safe (policy swap only).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "mt4_25_fix_rls_predicate"
down_revision: Union[str, Sequence[str], None] = "mt4_24_user_tenant_backfill"
branch_labels = None
depends_on = None

_NEW = (
    "NULLIF(current_setting('app.current_tenant', true), '') IS NULL "
    "OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
)
_OLD = (
    "current_setting('app.current_tenant', true) IS NULL "
    "OR current_setting('app.current_tenant', true) = '' "
    "OR tenant_id = current_setting('app.current_tenant', true)::uuid"
)


def _recreate(predicate: str) -> None:
    bind = op.get_bind()
    tables = [r[0] for r in bind.execute(sa.text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' AND rowsecurity=true "
        "ORDER BY tablename"
    ))]
    for t in tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"CREATE POLICY tenant_isolation ON {t} USING ({predicate}) WITH CHECK ({predicate})")


def upgrade() -> None:
    _recreate(_NEW)


def downgrade() -> None:
    _recreate(_OLD)
