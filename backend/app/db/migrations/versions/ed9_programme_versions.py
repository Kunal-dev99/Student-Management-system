"""Effective dating, Phase 8b: programme versions and cohort pinning (Demo 2 item 1.3, the CMA rule).

- programme_version: what a programme promised (total credits, duration, grading policy, module
  structure) over [valid_from, valid_to).
- student_programme_pin: the version a student is on for a programme, fixed when they started on it.
- Backfill: every programme gets version 1 from its current rules and modules, starting at the
  earlier of the academic year it was created in and its first student's start; every student is
  pinned to version 1 of each programme in their (live) programme history, from the day they started
  on it, plus their current programme if it has no history.

Revision ID: ed9_programme_versions
Revises: ed8_module_versions
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "ed9_programme_versions"
down_revision: Union[str, Sequence[str], None] = "ed8_module_versions"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.ed9")
_TABLES = ("programme_version", "student_programme_pin")


def _common() -> list:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "programme_version", *_common(),
        sa.Column("programme_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("taught_total_credits", sa.Integer(), nullable=True),
        sa.Column("duration_months", sa.Integer(), nullable=True),
        sa.Column("grading_policy", sa.JSON(), nullable=True),
        sa.Column("structure", sa.JSON(), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["programme_id"], ["programme.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("programme_id", "version_no", name="uq_programme_version_no"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_period"),
    )
    op.create_index(op.f("ix_programme_version_tenant_id"), "programme_version", ["tenant_id"])
    op.create_index(op.f("ix_programme_version_programme_id"), "programme_version", ["programme_id"])
    op.create_index("ix_programme_version_programme_from", "programme_version", ["programme_id", "valid_from"])

    op.create_table(
        "student_programme_pin", *_common(),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("programme_id", sa.Uuid(), nullable=False),
        sa.Column("programme_version_id", sa.Uuid(), nullable=False),
        sa.Column("pinned_on", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["programme_id"], ["programme.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["programme_version_id"], ["programme_version.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("student_id", "programme_id", name="uq_student_programme_pin"),
    )
    op.create_index(op.f("ix_student_programme_pin_tenant_id"), "student_programme_pin", ["tenant_id"])
    op.create_index(op.f("ix_student_programme_pin_student_id"), "student_programme_pin", ["student_id"])
    op.create_index(op.f("ix_student_programme_pin_programme_id"), "student_programme_pin", ["programme_id"])
    op.create_index(op.f("ix_student_programme_pin_programme_version_id"), "student_programme_pin",
                    ["programme_version_id"])

    if bind.dialect.name != "postgresql":
        return
    enable_rls(_TABLES)

    ay_of = ("make_date(CASE WHEN EXTRACT(MONTH FROM {d}) >= 8 THEN CAST(EXTRACT(YEAR FROM {d}) AS INT) "
             "ELSE CAST(EXTRACT(YEAR FROM {d}) AS INT) - 1 END, 8, 1)")
    n_versions = bind.execute(sa.text(f"""
        INSERT INTO programme_version (id, tenant_id, programme_id, version_no, valid_from,
                                       taught_total_credits, duration_months, grading_policy,
                                       structure, change_note)
        SELECT gen_random_uuid(), p.tenant_id, p.id, 1,
               LEAST({ay_of.format(d='p.created_at')},
                     COALESCE((SELECT MIN({ay_of.format(d='s.start_date')}) FROM student s
                               WHERE s.programme_id = p.id AND s.start_date IS NOT NULL),
                              {ay_of.format(d='p.created_at')})),
               p.taught_total_credits, p.duration_months, p.grading_policy,
               (SELECT COALESCE(json_agg(json_build_object('moduleId', CAST(x.id AS TEXT), 'code', x.code,
                                                           'isCore', x.is_core) ORDER BY x.code),
                                CAST('[]' AS json))
                FROM (SELECT m.id, m.code, m.is_core FROM taught_module m WHERE m.programme_id = p.id
                      UNION ALL
                      SELECT m.id, m.code, false FROM module_offering o
                      JOIN taught_module m ON m.id = o.module_id
                      WHERE o.programme_id = p.id AND m.programme_id <> p.id) x),
               'First version (rebuilt from existing data)'
        FROM programme p
        WHERE NOT EXISTS (SELECT 1 FROM programme_version v WHERE v.programme_id = p.id)
    """)).rowcount
    # Pins: every programme in a student's live programme history, from when they started on it,
    # plus the current programme of anyone without history.
    n_pins = bind.execute(sa.text("""
        INSERT INTO student_programme_pin (id, tenant_id, student_id, programme_id,
                                           programme_version_id, pinned_on)
        SELECT gen_random_uuid(), s.tenant_id, x.student_id, x.programme_id, v.id, x.started
        FROM (
            SELECT h.student_id, h.programme_id, MIN(h.valid_from) AS started
            FROM student_programme_history h
            WHERE h.superseded_by IS NULL AND h.programme_id IS NOT NULL
            GROUP BY h.student_id, h.programme_id
            UNION ALL
            SELECT s2.id, s2.programme_id, COALESCE(s2.start_date, CAST(s2.created_at AS DATE))
            FROM student s2
            WHERE s2.programme_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM student_programme_history h2
                WHERE h2.student_id = s2.id AND h2.programme_id = s2.programme_id
                  AND h2.superseded_by IS NULL)
        ) x
        JOIN student s ON s.id = x.student_id
        JOIN programme_version v ON v.programme_id = x.programme_id AND v.version_no = 1
    """)).rowcount
    unpinned = bind.execute(sa.text("""
        SELECT count(*) FROM student s WHERE s.programme_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM student_programme_pin p
            WHERE p.student_id = s.id AND p.programme_id = s.programme_id)
    """)).scalar()
    log.info("Programme versions backfilled: %s versions, %s pins", n_versions, n_pins)
    if unpinned:
        raise RuntimeError(f"{unpinned} student(s) could not be pinned to a programme version")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        disable_rls(_TABLES)
    op.drop_table("student_programme_pin")
    op.drop_table("programme_version")
