"""CMP-1 — Composer audit table.

One row per composition attempt. Backs the per-user daily token budget, the "why did it
show me that?" disclosure, and the record of what was sent to a third-party model.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "cmp1_composer_run"
down_revision: Union[str, Sequence[str], None] = "mt1_tenant_skeleton"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "composer_run",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("composition_key", sa.String(80), nullable=True),
        sa.Column("functions_called", sa.JSON(), nullable=True),
        sa.Column("composition", sa.JSON(), nullable=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT",
                                name=op.f("fk_composer_run_tenant_id_tenant")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name=op.f("fk_composer_run_user_id_users")),
    )
    op.create_index("ix_composer_run_tenant_id", "composer_run", ["tenant_id"])
    op.create_index("ix_composer_run_user_id", "composer_run", ["user_id"])
    op.create_index("ix_composer_run_composition_key", "composer_run", ["composition_key"])
    # Budget queries filter by user and day — this is the index they land on.
    op.create_index("ix_composer_run_user_created", "composer_run", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_composer_run_user_created", table_name="composer_run")
    op.drop_index("ix_composer_run_composition_key", table_name="composer_run")
    op.drop_index("ix_composer_run_user_id", table_name="composer_run")
    op.drop_index("ix_composer_run_tenant_id", table_name="composer_run")
    op.drop_table("composer_run")
