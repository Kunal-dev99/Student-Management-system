"""Custom attribute governance, Phase 6: export usage.

``student_custom_field_usage`` records each time a return read a custom attribute for real
(generated, downloaded, signed off). Tenant-scoped, RLS. Feeds "last used" and the lifecycle
review.

Revision ID: ca3_custom_attribute_usage
Revises: ca2_custom_attribute_assessment
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "ca3_custom_attribute_usage"
down_revision: Union[str, Sequence[str], None] = "ca2_custom_attribute_assessment"
branch_labels = None
depends_on = None

_TABLE = "student_custom_field_usage"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("custom_field_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("profile_code", sa.String(length=40), nullable=False),
        sa.Column("academic_year", sa.String(length=9), nullable=False),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["custom_field_id"], ["student_custom_field.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["report_profile.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f(f"ix_{_TABLE}_tenant_id"), _TABLE, ["tenant_id"])
    op.create_index(op.f(f"ix_{_TABLE}_custom_field_id"), _TABLE, ["custom_field_id"])
    op.create_index("ix_custom_field_usage_field_used", _TABLE, ["custom_field_id", "used_at"])
    if op.get_bind().dialect.name == "postgresql":
        enable_rls((_TABLE,))


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        disable_rls((_TABLE,))
    op.drop_table(_TABLE)
