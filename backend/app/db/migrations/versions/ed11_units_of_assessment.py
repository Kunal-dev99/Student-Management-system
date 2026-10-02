"""Effective dating, Phase 9: units of assessment, with dated links for students and staff.

- unit_of_assessment: the institution's UOA list (code, name, panel, active).
- student_uoa_history / person_uoa_history: half-open periods, the same shape as the other
  history tables (RLS, closure flag, no-overlap constraint on live rows).
- student.uoa_id / person.uoa_id: today's value (cache).
No backfill: the UOA list starts empty and links are recorded from the screens.

Revision ID: ed11_units_of_assessment
Revises: ed10_module_fte
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "ed11_units_of_assessment"
down_revision: Union[str, Sequence[str], None] = "ed10_module_fte"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.ed11")
_HISTORY = (("student_uoa_history", "student_id", "student"), ("person_uoa_history", "person_id", "person"))


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "unit_of_assessment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("panel", sa.String(length=20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_uoa_tenant_code"),
    )
    op.create_index(op.f("ix_unit_of_assessment_tenant_id"), "unit_of_assessment", ["tenant_id"])

    for name, subject, subject_table in _HISTORY:
        op.create_table(
            name,
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=True),
            sa.Column(subject, sa.Uuid(), nullable=False),
            sa.Column("uoa_id", sa.Uuid(), nullable=False),
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
            sa.ForeignKeyConstraint([subject], [f"{subject_table}.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["uoa_id"], ["unit_of_assessment.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["source_event_id"], ["student_lifecycle_event.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["superseded_by"], [f"{name}.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_period"),
        )
        op.create_index(op.f(f"ix_{name}_tenant_id"), name, ["tenant_id"])
        op.create_index(op.f(f"ix_{name}_{subject}"), name, [subject])
        op.create_index(op.f(f"ix_{name}_uoa_id"), name, ["uoa_id"])
        short = subject.replace("_id", "")
        op.create_index(f"ix_{name}_{short}_from", name, [subject, "valid_from"])

    op.add_column("student", sa.Column("uoa_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_student_uoa", "student", "unit_of_assessment", ["uoa_id"], ["id"],
                          ondelete="SET NULL")
    op.add_column("person", sa.Column("uoa_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_person_uoa", "person", "unit_of_assessment", ["uoa_id"], ["id"],
                          ondelete="SET NULL")

    if bind.dialect.name != "postgresql":
        return
    enable_rls(("unit_of_assessment",) + tuple(n for n, _, _ in _HISTORY))
    for name, subject, _ in _HISTORY:
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


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        disable_rls(("unit_of_assessment",) + tuple(n for n, _, _ in _HISTORY))
    op.drop_constraint("fk_person_uoa", "person", type_="foreignkey")
    op.drop_column("person", "uoa_id")
    op.drop_constraint("fk_student_uoa", "student", type_="foreignkey")
    op.drop_column("student", "uoa_id")
    for name, _, _ in reversed(_HISTORY):
        op.drop_table(name)
    op.drop_table("unit_of_assessment")
