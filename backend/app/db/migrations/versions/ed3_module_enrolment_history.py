"""Effective dating, Phase 3: module enrolment dates and status history.

- module_enrolment_status gains ``interrupted`` (a module ended because the student suspended).
- module_enrolment gains start_date / end_date (the student's own inclusive dates on the module,
  HESA ModuleInstance MODINSTSTARTDATE / MODINSTENDDATE).
- module_enrolment_status_history: half-open status periods per enrolment, tenant-scoped with RLS,
  with a deferrable no-overlap exclusion constraint (skipped with a warning without btree_gist).
- Existing enrolments are dated and given a status history
  (app/modules/taught/module_backfill.py), then checked against their cached status.

Revision ID: ed3_module_enrolment_history
Revises: ed2_programme_intensity_history
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "ed3_module_enrolment_history"
down_revision: Union[str, Sequence[str], None] = "ed2_programme_intensity_history"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.ed3")
_TABLE = "module_enrolment_status_history"


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    if is_pg:
        op.execute("ALTER TYPE module_enrolment_status ADD VALUE IF NOT EXISTS 'interrupted'")
        status_type = postgresql.ENUM(name="module_enrolment_status", create_type=False)
    else:
        status_type = sa.String(length=20)

    op.add_column("module_enrolment", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("module_enrolment", sa.Column("end_date", sa.Date(), nullable=True))

    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("module_enrolment_id", sa.Uuid(), nullable=False),
        sa.Column("status", status_type, nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("origin", sa.String(length=20), nullable=False, server_default="change"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source_event_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["module_enrolment_id"], ["module_enrolment.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_event_id"], ["student_lifecycle_event.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["superseded_by"], [f"{_TABLE}.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_period"),
    )
    op.create_index(op.f(f"ix_{_TABLE}_tenant_id"), _TABLE, ["tenant_id"])
    op.create_index(op.f(f"ix_{_TABLE}_module_enrolment_id"), _TABLE, ["module_enrolment_id"])
    op.create_index(op.f(f"ix_{_TABLE}_source_event_id"), _TABLE, ["source_event_id"])
    op.create_index(f"ix_{_TABLE}_enrolment_from", _TABLE, ["module_enrolment_id", "valid_from"])

    if is_pg:
        enable_rls((_TABLE,))
        try:
            with bind.begin_nested():
                op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
                op.execute(
                    f"ALTER TABLE {_TABLE} ADD CONSTRAINT ex_{_TABLE}_no_overlap "
                    "EXCLUDE USING gist (module_enrolment_id WITH =, daterange(valid_from, valid_to, '[)') WITH &&) "
                    "WHERE (superseded_by IS NULL) DEFERRABLE INITIALLY DEFERRED"
                )
        except Exception as exc:   # noqa: BLE001 — optional hardening; the app checks overlaps too
            log.warning("No-overlap constraint on %s skipped: %s", _TABLE, exc)

    from app.modules.taught.module_backfill import backfill_module_enrolments, check_module_enrolments

    log.info("Module enrolments backfilled: %s", backfill_module_enrolments(bind))
    bad = check_module_enrolments(bind)
    if bad:
        raise RuntimeError(f"Module enrolment backfill disagrees with the cached status for {len(bad)} "
                           f"enrolment(s), e.g. {bad[:5]}")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        disable_rls((_TABLE,))
    op.drop_table(_TABLE)
    op.drop_column("module_enrolment", "end_date")
    op.drop_column("module_enrolment", "start_date")
    # 'interrupted' stays in module_enrolment_status: Postgres can't drop enum values.
