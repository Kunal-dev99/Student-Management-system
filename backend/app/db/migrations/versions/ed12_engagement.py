"""Effective dating, Phase 10: HESA Engagement (and Leaver) fields.

- student_expected_end_history: the expected end date as held over time (ENGEXPECTEDENDDATE).
- student_fee_eligibility_history / student_outside_uk_history: dated Engagement facts
  (FEEELIG, ENGPRINONUK).
- student: fee_eligibility / primarily_outside_uk (today's value), study_intention,
  incoming_exchange (fixed for the engagement).
- student_lifecycle_event.leaver_reason: why the engagement ended (withdrawal / termination).
- Backfill: every student with an expected end gets one period from their start date holding the
  current value (marked 'backfill'; earlier expectations weren't recorded).

Revision ID: ed12_engagement
Revises: ed11_units_of_assessment
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "ed12_engagement"
down_revision: Union[str, Sequence[str], None] = "ed11_units_of_assessment"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.ed12")
_TABLES = (
    ("student_expected_end_history", sa.Column("expected_end_date", sa.Date(), nullable=False)),
    ("student_fee_eligibility_history", sa.Column("fee_eligibility", sa.String(length=30), nullable=False)),
    ("student_outside_uk_history", sa.Column("primarily_outside_uk", sa.Boolean(), nullable=False)),
)


def upgrade() -> None:
    bind = op.get_bind()
    for name, value in _TABLES:
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
            sa.Column("closure", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_event_id"], ["student_lifecycle_event.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["superseded_by"], [f"{name}.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_period"),
        )
        op.create_index(op.f(f"ix_{name}_tenant_id"), name, ["tenant_id"])
        op.create_index(op.f(f"ix_{name}_student_id"), name, ["student_id"])
        op.create_index(f"ix_{name}_student_from", name, ["student_id", "valid_from"])

    op.add_column("student", sa.Column("fee_eligibility", sa.String(length=30), nullable=True))
    op.add_column("student", sa.Column("primarily_outside_uk", sa.Boolean(), nullable=True))
    op.add_column("student", sa.Column("study_intention", sa.String(length=40), nullable=True))
    op.add_column("student", sa.Column("incoming_exchange", sa.Boolean(), nullable=True))
    op.add_column("student_lifecycle_event", sa.Column("leaver_reason", sa.String(length=32), nullable=True))

    if bind.dialect.name != "postgresql":
        return
    names = tuple(n for n, _ in _TABLES)
    enable_rls(names)
    for name in names:
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

    n = bind.execute(sa.text("""
        INSERT INTO student_expected_end_history
            (id, tenant_id, student_id, expected_end_date, valid_from, origin, reason)
        SELECT gen_random_uuid(), s.tenant_id, s.id, s.expected_end_date,
               COALESCE(s.start_date, CAST(s.created_at AS DATE)), 'backfill',
               'Expected end held when history began'
        FROM student s
        WHERE s.expected_end_date IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM student_expected_end_history h WHERE h.student_id = s.id)
    """)).rowcount
    log.info("Expected end history backfilled: %s student(s)", n)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        disable_rls(tuple(n for n, _ in _TABLES))
    op.drop_column("student_lifecycle_event", "leaver_reason")
    for col in ("incoming_exchange", "study_intention", "primarily_outside_uk", "fee_eligibility"):
        op.drop_column("student", col)
    for name, _ in reversed(_TABLES):
        op.drop_table(name)
