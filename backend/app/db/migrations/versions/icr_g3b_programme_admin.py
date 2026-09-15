"""ICR G3 (slice B) - programme admin fields.

Additive: programme.duration_months (expected duration, drives a new student's expected end date)
and programme.supervision_meeting_interval_days (per-programme override of the institution-wide
supervision cadence; NULL = use the global setting). Nothing existing changes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "icr_g3b_programme_admin"
down_revision: Union[str, Sequence[str], None] = "icr_g3_milestone_overrides"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("programme", sa.Column("duration_months", sa.Integer(), nullable=True))
    op.add_column(
        "programme",
        sa.Column("supervision_meeting_interval_days", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("programme", "supervision_meeting_interval_days")
    op.drop_column("programme", "duration_months")
