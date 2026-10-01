"""Effective dating, Phase 1: student status history.

- student_status gains ``writing_up``; lifecycle_event_type gains ``writing_up``, ``withdrawal``
  and ``termination`` (Postgres ADD VALUE; the new values aren't used in this transaction).
- student_status_history: half-open status periods, tenant-scoped with RLS.
- A PostgreSQL exclusion constraint forbids overlapping live periods per student. It is
  DEFERRABLE INITIALLY DEFERRED because a change closes one period and opens the next in one
  transaction. Needs btree_gist; if the extension can't be created (permissions), the constraint
  is skipped and the application's own overlap check still applies.
- The ``student.history.correct`` permission is added and granted to the all-access roles, so
  existing databases get it without re-running the seed.
- Existing students are backfilled (see app/modules/student_record/status_backfill.py), then
  checked: the migration fails if any cached status disagrees with its history for today.

Revision ID: ed1_status_history
Revises: cf1_student_custom_fields
"""
from __future__ import annotations

import logging
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "ed1_status_history"
down_revision: Union[str, Sequence[str], None] = "cf1_student_custom_fields"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.ed1")
_TABLE = "student_status_history"
_PERMISSION = "student.history.correct"


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        op.execute("ALTER TYPE student_status ADD VALUE IF NOT EXISTS 'writing_up'")
        for v in ("writing_up", "withdrawal", "termination"):
            op.execute(f"ALTER TYPE lifecycle_event_type ADD VALUE IF NOT EXISTS '{v}'")
        status_type = postgresql.ENUM(name="student_status", create_type=False)
    else:
        status_type = sa.String(length=20)

    op.create_table(
        _TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("student_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_event_id"], ["student_lifecycle_event.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["superseded_by"], [f"{_TABLE}.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_period"),
    )
    op.create_index(op.f(f"ix_{_TABLE}_tenant_id"), _TABLE, ["tenant_id"])
    op.create_index(op.f(f"ix_{_TABLE}_student_id"), _TABLE, ["student_id"])
    op.create_index(op.f(f"ix_{_TABLE}_source_event_id"), _TABLE, ["source_event_id"])
    op.create_index(f"ix_{_TABLE}_student_from", _TABLE, ["student_id", "valid_from"])

    if is_pg:
        enable_rls((_TABLE,))
        try:
            with bind.begin_nested():
                op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
                op.execute(
                    f"ALTER TABLE {_TABLE} ADD CONSTRAINT ex_{_TABLE}_no_overlap "
                    "EXCLUDE USING gist (student_id WITH =, daterange(valid_from, valid_to, '[)') WITH &&) "
                    "WHERE (superseded_by IS NULL) DEFERRABLE INITIALLY DEFERRED"
                )
        except Exception as exc:   # noqa: BLE001 — optional hardening; the app checks overlaps too
            log.warning("No-overlap constraint skipped (btree_gist unavailable?): %s", exc)

    _grant_permission(bind)

    from app.modules.student_record.status_backfill import (
        backfill_status_history,
        check_status_history,
    )

    result = backfill_status_history(bind)
    log.info("Status history backfilled: %s", result)
    bad = check_status_history(bind)
    if bad:
        raise RuntimeError(f"Status history backfill disagrees with student.status for {len(bad)} "
                           f"student(s), e.g. {bad[:5]}")


def _grant_permission(bind) -> None:
    # Separate, explicitly typed parameters: asyncpg can't infer one type for a parameter used
    # both as a selected value and in a comparison.
    bind.execute(
        sa.text("INSERT INTO permission (id, code, description) "
                "SELECT :id, CAST(:code AS VARCHAR), CAST(:description AS VARCHAR) "
                "WHERE NOT EXISTS (SELECT 1 FROM permission WHERE code = CAST(:code_check AS VARCHAR))"),
        {"id": uuid.uuid4(), "code": _PERMISSION, "code_check": _PERMISSION,
         "description": "Correct a student's recorded status history (dates or values)"},
    )
    bind.execute(
        sa.text("INSERT INTO role_permission (role_id, permission_id) "
                "SELECT r.id, p.id FROM role r, permission p "
                "WHERE p.code = :code AND r.name IN ('Institution Administrator', 'dev') "
                "AND NOT EXISTS (SELECT 1 FROM role_permission rp "
                "                WHERE rp.role_id = r.id AND rp.permission_id = p.id)"),
        {"code": _PERMISSION},
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        disable_rls((_TABLE,))
    op.drop_table(_TABLE)
    bind.execute(sa.text("DELETE FROM permission WHERE code = :code"), {"code": _PERMISSION})
    # Enum values added to student_status / lifecycle_event_type stay: Postgres can't drop them.
