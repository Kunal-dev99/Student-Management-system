"""MT-2 — Spread tenant_id across the core student spine (person, programme, student, department).

Additive and non-breaking, exactly like MT-1:

* `tenant_id` is nullable, so existing rows and existing code keep working.
* every existing row is backfilled to the default tenant.
* an index + FK per table (RESTRICT so a tenant can't be deleted out from under its data).

This does NOT enable row-level security — isolation is switched on in a later, separately
verified step (MT-3) once tenant_id has spread far enough and the isolation tests are green.
The point here is to lay the column + backfill so the ORM can stamp new rows and RLS has a
column to match on, with zero behaviour change for the running single-tenant deployment.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "mt2_tenant_scope_core"
down_revision: Union[str, Sequence[str], None] = "taught_module_offering"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"

# Core tenant-owned tables scoped in this slice. The pattern replicates verbatim to the
# rest of the domain in follow-up migrations.
_TABLES: tuple[str, ...] = ("person", "programme", "student", "department")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("tenant_id", sa.UUID(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_tenant_id", table, "tenant", ["tenant_id"], ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        # Backfill every existing row to the default tenant.
        op.execute(sa.text(
            f"UPDATE {table} SET tenant_id = CAST(:tid AS uuid) WHERE tenant_id IS NULL"
        ).bindparams(tid=DEFAULT_TENANT_ID))


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_constraint(f"fk_{table}_tenant_id", table, type_="foreignkey")
        op.drop_column(table, "tenant_id")
