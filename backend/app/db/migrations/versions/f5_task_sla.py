"""F5 — Task SLA clock columns."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f5_task_sla"
down_revision: Union[str, Sequence[str], None] = "f4_award_classification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("task", sa.Column("sla_target_seconds", sa.Integer(), nullable=True))
    op.add_column("task", sa.Column("sla_working_days_only", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("task", sa.Column("sla_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("task", sa.Column("sla_breached", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_index(op.f("ix_task_sla_breached"), "task", ["sla_breached"])


def downgrade() -> None:
    op.drop_index(op.f("ix_task_sla_breached"), table_name="task")
    op.drop_column("task", "sla_breached")
    op.drop_column("task", "sla_started_at")
    op.drop_column("task", "sla_working_days_only")
    op.drop_column("task", "sla_target_seconds")
