"""Editable overrides for platform value sets — labels, descriptions, hidden flag."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "value_set_overrides"
down_revision: Union[str, Sequence[str], None] = "portal_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "value_set_override",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("enum_name", sa.String(length=100), nullable=False),
        sa.Column("value_code", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("hidden", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("enum_name", "value_code", name="uq_value_set_override_enum_code"),
    )
    op.create_index("ix_value_set_override_enum_name", "value_set_override", ["enum_name"])


def downgrade() -> None:
    op.drop_index("ix_value_set_override_enum_name", table_name="value_set_override")
    op.drop_table("value_set_override")
