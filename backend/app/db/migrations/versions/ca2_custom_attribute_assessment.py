"""Custom attribute governance, Phase 2: stored necessity assessments.

``student_custom_field_assessment`` keeps each run of the duplicate / HESA / type check for a
requested attribute (tenant-scoped, RLS). The latest row is what the approver sees.

Revision ID: ca2_custom_attribute_assessment
Revises: ca1_custom_attribute_governance
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "ca2_custom_attribute_assessment"
down_revision: Union[str, Sequence[str], None] = "ca1_custom_attribute_governance"
branch_labels = None
depends_on = None

_TABLE = "student_custom_field_assessment"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("custom_field_id", sa.Uuid(), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("specification", sa.String(length=80), nullable=True),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("assessed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["custom_field_id"], ["student_custom_field.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f(f"ix_{_TABLE}_tenant_id"), _TABLE, ["tenant_id"])
    op.create_index(op.f(f"ix_{_TABLE}_custom_field_id"), _TABLE, ["custom_field_id"])
    if op.get_bind().dialect.name == "postgresql":
        enable_rls((_TABLE,))


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        disable_rls((_TABLE,))
    op.drop_table(_TABLE)
