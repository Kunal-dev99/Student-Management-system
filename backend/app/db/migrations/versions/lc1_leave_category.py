"""LC-1 — leave category on suspension lifecycle events.

Adds a nullable ``leave_category`` column to ``student_lifecycle_event`` so a suspension can
be tagged as medical / personal / academic / other. Every other event type leaves it NULL —
the vocabulary and its enforcement live in the API schema (not the DB) so an institution
can extend the list in configuration without a schema change.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "lc1_leave_category"
down_revision: Union[str, Sequence[str], None] = "pt1_programme_change"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "student_lifecycle_event",
        sa.Column("leave_category", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("student_lifecycle_event", "leave_category")
