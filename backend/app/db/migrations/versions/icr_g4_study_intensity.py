"""ICR G4 - study intensity (FTE %) over time.

Additive:
- new lifecycle_event_type value 'intensity_change'
- student_lifecycle_event.previous_intensity_pct / intensity_pct (the % before and after)

Existing suspension/extension/mode_change events are untouched (both columns NULL for them).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "icr_g4_study_intensity"
down_revision: Union[str, Sequence[str], None] = "icr_g3b_programme_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PG 12+ allows ADD VALUE inside a transaction as long as the value is not used in the same
    # transaction (it isn't here). No-op-safe with IF NOT EXISTS.
    op.execute("ALTER TYPE lifecycle_event_type ADD VALUE IF NOT EXISTS 'intensity_change'")
    op.add_column(
        "student_lifecycle_event",
        sa.Column("previous_intensity_pct", sa.Integer(), nullable=True),
    )
    op.add_column(
        "student_lifecycle_event",
        sa.Column("intensity_pct", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("student_lifecycle_event", "intensity_pct")
    op.drop_column("student_lifecycle_event", "previous_intensity_pct")
    # Postgres cannot drop an enum value; 'intensity_change' is left in place (harmless).
