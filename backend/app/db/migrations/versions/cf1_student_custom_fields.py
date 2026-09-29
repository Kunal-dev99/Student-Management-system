"""Admin-defined custom student attributes (HESA gap capture).

Two tenant-scoped tables: `student_custom_field` (definitions) + `student_custom_value` (one value
per student per field). Lets an admin capture an attribute a statutory return needs but the core
model doesn't hold — without a runtime schema change. RLS is enabled to match every other
tenant-owned table.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "cf1_student_custom_fields"
down_revision: Union[str, Sequence[str], None] = "mt7_users_rls"
branch_labels = None
depends_on = None

_TABLES = ("student_custom_field", "student_custom_value")


def upgrade() -> None:
    op.create_table(
        "student_custom_field",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("data_type", sa.String(length=20), nullable=False, server_default="string"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_custom_field_tenant_key"),
    )
    op.create_index(op.f("ix_student_custom_field_tenant_id"), "student_custom_field", ["tenant_id"])
    op.create_index(op.f("ix_student_custom_field_key"), "student_custom_field", ["key"])

    op.create_table(
        "student_custom_value",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("custom_field_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["custom_field_id"], ["student_custom_field.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("custom_field_id", "student_id", name="uq_custom_value_field_student"),
    )
    op.create_index(op.f("ix_student_custom_value_tenant_id"), "student_custom_value", ["tenant_id"])
    op.create_index(op.f("ix_student_custom_value_custom_field_id"), "student_custom_value", ["custom_field_id"])
    op.create_index(op.f("ix_student_custom_value_student_id"), "student_custom_value", ["student_id"])

    enable_rls(_TABLES)


def downgrade() -> None:
    disable_rls(_TABLES)
    op.drop_table("student_custom_value")
    op.drop_table("student_custom_field")
