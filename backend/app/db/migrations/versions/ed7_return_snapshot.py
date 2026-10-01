"""Effective dating, Phase 7: HESA snapshot — returns "as at" a date and "as known at" a moment.

- ``closure`` on every history table: a period that ends is now superseded by a closed copy instead
  of having ``valid_to`` edited in place, so the data can be rebuilt exactly as it was recorded at
  any moment. Rows written before this migration were closed in place; they are left as they are.
- ``ended_at`` on funding_arrangement and supervisor_relationship: when ``valid_to`` was set.
  Backfilled from ``updated_at`` for rows already ended (the closest record we have).
- ``report_return_version``: the exact return frozen at sign-off (tenant-scoped, RLS).

Revision ID: ed7_return_snapshot
Revises: ed6_fee_location_custom_history
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "ed7_return_snapshot"
down_revision: Union[str, Sequence[str], None] = "ed6_fee_location_custom_history"
branch_labels = None
depends_on = None

_HISTORY = (
    "student_status_history", "student_programme_history", "student_intensity_history",
    "module_enrolment_status_history", "student_fee_status_history", "student_location_history",
    "student_custom_value_history",
)
_ENDED = ("funding_arrangement", "supervisor_relationship")


def upgrade() -> None:
    bind = op.get_bind()
    for t in _HISTORY:
        op.add_column(t, sa.Column("closure", sa.Boolean(), nullable=False, server_default=sa.false()))
    for t in _ENDED:
        op.add_column(t, sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))
        op.execute(f"UPDATE {t} SET ended_at = updated_at WHERE valid_to IS NOT NULL AND ended_at IS NULL")

    op.create_table(
        "report_return_version",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("academic_year", sa.String(length=9), nullable=False),
        sa.Column("as_at", sa.Date(), nullable=True),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False, server_default="sign_off"),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("header", sa.JSON(), nullable=False),
        sa.Column("rows", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warnings", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["profile_id"], ["report_profile.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_report_return_version_tenant_id"), "report_return_version", ["tenant_id"])
    op.create_index(op.f("ix_report_return_version_profile_id"), "report_return_version", ["profile_id"])
    op.create_index("uq_report_return_version", "report_return_version", ["profile_id", "version_no"],
                    unique=True)
    if bind.dialect.name == "postgresql":
        enable_rls(("report_return_version",))


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        disable_rls(("report_return_version",))
    op.drop_table("report_return_version")
    for t in _ENDED:
        op.drop_column(t, "ended_at")
    for t in _HISTORY:
        op.drop_column(t, "closure")
