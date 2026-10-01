"""Effective dating, Phase 2: programme and study-intensity history.

- student_programme_history and student_intensity_history: half-open periods, tenant-scoped with
  RLS, the same shape as student_status_history (ed1).
- PostgreSQL exclusion constraints forbid overlapping live periods per student (DEFERRABLE
  INITIALLY DEFERRED; skipped with a warning if btree_gist can't be created).
- Existing students are backfilled (app/modules/student_record/fact_backfill.py), then checked: the
  migration fails if any cached programme / study mode disagrees with its history for today.

Revision ID: ed2_programme_intensity_history
Revises: ed1_status_history
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "ed2_programme_intensity_history"
down_revision: Union[str, Sequence[str], None] = "ed1_status_history"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.ed2")
_TABLES = ("student_programme_history", "student_intensity_history")


def _history_table(name: str, value: sa.Column, extra_fks: list) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        value,
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("origin", sa.String(length=20), nullable=False, server_default="change"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source_event_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_event_id"], ["student_lifecycle_event.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["superseded_by"], [f"{name}.id"], ondelete="SET NULL"),
        *extra_fks,
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_period"),
    )
    op.create_index(op.f(f"ix_{name}_tenant_id"), name, ["tenant_id"])
    op.create_index(op.f(f"ix_{name}_student_id"), name, ["student_id"])
    op.create_index(op.f(f"ix_{name}_source_event_id"), name, ["source_event_id"])
    op.create_index(f"ix_{name}_student_from", name, ["student_id", "valid_from"])


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    _history_table(
        "student_programme_history", sa.Column("programme_id", sa.Uuid(), nullable=True),
        [sa.ForeignKeyConstraint(["programme_id"], ["programme.id"], ondelete="RESTRICT")],
    )
    op.create_index(op.f("ix_student_programme_history_programme_id"),
                    "student_programme_history", ["programme_id"])
    _history_table(
        "student_intensity_history", sa.Column("intensity_pct", sa.Integer(), nullable=False), [],
    )

    if is_pg:
        enable_rls(_TABLES)
        for name in _TABLES:
            try:
                with bind.begin_nested():
                    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
                    op.execute(
                        f"ALTER TABLE {name} ADD CONSTRAINT ex_{name}_no_overlap "
                        "EXCLUDE USING gist (student_id WITH =, daterange(valid_from, valid_to, '[)') WITH &&) "
                        "WHERE (superseded_by IS NULL) DEFERRABLE INITIALLY DEFERRED"
                    )
            except Exception as exc:   # noqa: BLE001 — optional hardening; the app checks overlaps too
                log.warning("No-overlap constraint on %s skipped: %s", name, exc)

    from app.modules.student_record.fact_backfill import (
        backfill_programme_and_intensity,
        check_programme_and_intensity,
    )

    log.info("Programme / intensity history backfilled: %s", backfill_programme_and_intensity(bind))
    bad = check_programme_and_intensity(bind)
    if bad:
        raise RuntimeError(f"Programme / intensity backfill disagrees with the cached values for "
                           f"{len(bad)} case(s), e.g. {bad[:5]}")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        disable_rls(_TABLES)
    for name in reversed(_TABLES):
        op.drop_table(name)
