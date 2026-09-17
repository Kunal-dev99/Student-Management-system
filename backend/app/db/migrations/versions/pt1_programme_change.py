"""PT-1 — mid-term programme transfer.

Extends ``StudentLifecycleEvent`` so a mid-term move to a different programme (MPhil -> PhD, or
even PhD -> MSc) rides the same request -> approve -> recalculate pipeline as suspensions and
extensions. Additive:

- new ``lifecycle_event_type`` value ``programme_change``
- new ``milestone_status`` value ``cancelled`` — used for undecided milestones that are
  superseded by the transfer (decided milestones stay put as historical facts)
- three nullable columns on ``student_lifecycle_event``: ``previous_programme_id``,
  ``new_programme_id``, ``effective_date`` — populated only for programme_change events.

The existing per-type columns (days_applied, previous_mode, intensity_pct, …) remain NULL for a
programme_change; the student's current programme pointer stays on ``student.programme_id`` so
every downstream consumer (dashboards, milestones, taught modules) keeps reading it unchanged.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "pt1_programme_change"
down_revision: Union[str, Sequence[str], None] = "w4_rule_suppressions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # 1) new enum values — Postgres only; SQLite uses CHECK constraints regenerated from the model.
    if is_pg:
        op.execute("ALTER TYPE lifecycle_event_type ADD VALUE IF NOT EXISTS 'programme_change'")
        op.execute("ALTER TYPE milestone_status ADD VALUE IF NOT EXISTS 'cancelled'")

    # 2) new columns on the lifecycle event table — nullable, populated only for programme_change.
    op.add_column(
        "student_lifecycle_event",
        sa.Column("previous_programme_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "student_lifecycle_event",
        sa.Column("new_programme_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "student_lifecycle_event",
        sa.Column("effective_date", sa.Date(), nullable=True),
    )
    op.create_foreign_key(
        "fk_lifecycle_prev_programme",
        "student_lifecycle_event", "programme",
        ["previous_programme_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_lifecycle_new_programme",
        "student_lifecycle_event", "programme",
        ["new_programme_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_lifecycle_new_programme", "student_lifecycle_event", type_="foreignkey")
    op.drop_constraint("fk_lifecycle_prev_programme", "student_lifecycle_event", type_="foreignkey")
    op.drop_column("student_lifecycle_event", "effective_date")
    op.drop_column("student_lifecycle_event", "new_programme_id")
    op.drop_column("student_lifecycle_event", "previous_programme_id")
    # Postgres cannot drop an enum value; 'programme_change' and 'cancelled' stay in place
    # (harmless — no rows reference them once the columns are dropped).
