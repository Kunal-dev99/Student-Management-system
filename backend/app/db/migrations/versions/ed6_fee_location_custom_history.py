"""Effective dating, Phase 6: fee status, study location and opt-in custom attribute history.

- student.fee_status / student.study_location: cached values of two optional dated facts.
- student_fee_status_history / student_location_history: half-open periods per student, the same
  shape as the other history tables (RLS, no-overlap constraint on live rows).
- student_custom_field.track_history (default off) and student_custom_value_history: dated values
  of the custom attributes that opt in; the subject is the student's value row.
- Backfill: a student's fee status is taken from their most recent application that recorded one
  (not 'unknown'), from the student's start date, marked origin 'backfill'. Location has no source
  yet and starts empty.

Revision ID: ed6_fee_location_custom_history
Revises: ed5_returns_amend_permission
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "ed6_fee_location_custom_history"
down_revision: Union[str, Sequence[str], None] = "ed5_returns_amend_permission"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.ed6")

# (table, subject column, subject table)
_TABLES = (
    ("student_fee_status_history", "student_id", "student"),
    ("student_location_history", "student_id", "student"),
    ("student_custom_value_history", "custom_value_id", "student_custom_value"),
)


def _history_table(name: str, subject: str, subject_table: str, value: sa.Column) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column(subject, sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint([subject], [f"{subject_table}.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_event_id"], ["student_lifecycle_event.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["superseded_by"], [f"{name}.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_period"),
    )
    op.create_index(op.f(f"ix_{name}_tenant_id"), name, ["tenant_id"])
    op.create_index(op.f(f"ix_{name}_{subject}"), name, [subject])
    short = "value" if subject == "custom_value_id" else "student"
    op.create_index(f"ix_{name}_{short}_from", name, [subject, "valid_from"])


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.add_column("student", sa.Column("fee_status", sa.String(length=30), nullable=True))
    op.add_column("student", sa.Column("study_location", sa.String(length=60), nullable=True))
    op.add_column("student_custom_field",
                  sa.Column("track_history", sa.Boolean(), nullable=False, server_default=sa.false()))

    _history_table("student_fee_status_history", "student_id", "student",
                   sa.Column("fee_status", sa.String(length=30), nullable=False))
    _history_table("student_location_history", "student_id", "student",
                   sa.Column("study_location", sa.String(length=60), nullable=False))
    _history_table("student_custom_value_history", "custom_value_id", "student_custom_value",
                   sa.Column("value", sa.Text(), nullable=False))
    for name in ("student_fee_status_history", "student_location_history"):
        op.create_index(op.f(f"ix_{name}_source_event_id"), name, ["source_event_id"])

    if is_pg:
        enable_rls(tuple(t for t, _, _ in _TABLES))
        for name, subject, _ in _TABLES:
            try:
                with bind.begin_nested():
                    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
                    op.execute(
                        f"ALTER TABLE {name} ADD CONSTRAINT ex_{name}_no_overlap "
                        f"EXCLUDE USING gist ({subject} WITH =, daterange(valid_from, valid_to, '[)') WITH &&) "
                        "WHERE (superseded_by IS NULL) DEFERRABLE INITIALLY DEFERRED"
                    )
            except Exception as exc:   # noqa: BLE001 — optional hardening; the app checks overlaps too
                log.warning("No-overlap constraint on %s skipped: %s", name, exc)

        # Fee status from the latest application that recorded one.
        bind.execute(sa.text("""
            UPDATE student s SET fee_status = a.fee_status
            FROM (
                SELECT DISTINCT ON (person_id) person_id, CAST(fee_status AS VARCHAR) AS fee_status
                FROM application
                WHERE CAST(fee_status AS VARCHAR) <> 'unknown'
                ORDER BY person_id, COALESCE(submitted_at, created_at) DESC
            ) a
            WHERE a.person_id = s.person_id AND s.fee_status IS NULL
        """))
        n = bind.execute(sa.text("""
            INSERT INTO student_fee_status_history
                (id, tenant_id, student_id, fee_status, valid_from, origin, reason)
            SELECT gen_random_uuid(), s.tenant_id, s.id, s.fee_status,
                   COALESCE(s.start_date, CAST(s.created_at AS DATE)), 'backfill',
                   'From the admission record'
            FROM student s
            WHERE s.fee_status IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM student_fee_status_history h WHERE h.student_id = s.id)
        """)).rowcount
        log.info("Fee status history backfilled: %s student(s)", n)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        disable_rls(tuple(t for t, _, _ in _TABLES))
    for name, _, _ in reversed(_TABLES):
        op.drop_table(name)
    op.drop_column("student_custom_field", "track_history")
    op.drop_column("student", "study_location")
    op.drop_column("student", "fee_status")
