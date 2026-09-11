"""MT-1 — Multi-tenant skeleton (Phase 1).

Introduces the `tenant` table + a nullable `tenant_id` FK on `user`, then seeds a single
"default" tenant and backfills every existing user to it. This is DELIBERATELY skeletal:

* no other domain table is touched yet — everything continues to work single-tenant style.
* `tenant_id` on `user` is nullable so existing tests / seeds keep passing.
* RLS is NOT enabled yet — that arrives in Phase 2 when we spread tenant_id across the
  rest of the domain.

The point of this migration is to lay the plumbing (schema, model, seed) so future
phases can enable per-table isolation without a re-architecture.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "mt1_tenant_skeleton"
down_revision: Union[str, Sequence[str], None] = "cb_assistant_vocab_review"
branch_labels = None
depends_on = None


DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_TENANT_NAME = "Default Institution"
DEFAULT_TENANT_SUBDOMAIN = "default"


def upgrade() -> None:
    # -- Tenant table -----------------------------------------------------------
    op.create_table(
        "tenant",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("subdomain", sa.String(80), nullable=False, unique=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("branding", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_tenant_subdomain", "tenant", ["subdomain"], unique=True)

    # -- Seed the default tenant ------------------------------------------------
    op.execute(sa.text(
        "INSERT INTO tenant (id, name, subdomain, activated_at) "
        "VALUES (CAST(:id AS uuid), :name, :sub, CURRENT_TIMESTAMP)"
    ).bindparams(
        id=DEFAULT_TENANT_ID, name=DEFAULT_TENANT_NAME, sub=DEFAULT_TENANT_SUBDOMAIN,
    ))

    # -- Add nullable tenant_id FK to user + backfill --------------------------
    op.add_column("users", sa.Column("tenant_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_user_tenant_id", "users", "tenant", ["tenant_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_index("ix_user_tenant_id", "users", ["tenant_id"])

    # Backfill every existing user to the default tenant.
    op.execute(sa.text(
        "UPDATE users SET tenant_id = CAST(:tid AS uuid) WHERE tenant_id IS NULL"
    ).bindparams(tid=DEFAULT_TENANT_ID))


def downgrade() -> None:
    op.drop_index("ix_user_tenant_id", table_name="users")
    op.drop_constraint("fk_user_tenant_id", "users", type_="foreignkey")
    op.drop_column("users", "tenant_id")
    op.drop_index("ix_tenant_subdomain", table_name="tenant")
    op.drop_table("tenant")
