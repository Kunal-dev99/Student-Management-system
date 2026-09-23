"""Shared/elective taught modules — module_offering link table.

Additive only: a module keeps its single home programme (taught_module.programme_id); this table
lets the same module be OFFERED on other programmes as an elective. Programmes with no offerings
behave exactly as before.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "taught_module_offering"
down_revision: Union[str, Sequence[str], None] = "lc1_leave_category"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "module_offering",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("programme_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["programme_id"], ["programme.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["module_id"], ["taught_module.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("programme_id", "module_id", name="uq_module_offering_programme_module"),
    )
    op.create_index("ix_module_offering_programme_id", "module_offering", ["programme_id"])
    op.create_index("ix_module_offering_module_id", "module_offering", ["module_id"])


def downgrade() -> None:
    op.drop_index("ix_module_offering_module_id", table_name="module_offering")
    op.drop_index("ix_module_offering_programme_id", table_name="module_offering")
    op.drop_table("module_offering")
