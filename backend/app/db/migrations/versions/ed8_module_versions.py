"""Effective dating, Phase 8a: module versions and yearly runs (Demo 2 item 1.3, the CMA rule).

- module_version: what a module teaches (title, credits, level, term) over [valid_from, valid_to).
- module_run: a version taught in an academic year; module_enrolment.module_run_id links to it.
- Backfill: every module gets version 1 from its current values, starting at the earlier of the
  academic year it was created in and its first enrolment year; one run per module and academic
  year that has enrolments; every enrolment is linked to its run.

Revision ID: ed8_module_versions
Revises: ed7_return_snapshot
"""
from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.db.tenant_ddl import disable_rls, enable_rls

revision: str = "ed8_module_versions"
down_revision: Union[str, Sequence[str], None] = "ed7_return_snapshot"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.ed8")
_TABLES = ("module_version", "module_run")


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
        "module_version", *_common(),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("level", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("term", sa.String(length=60), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["module_id"], ["taught_module.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("module_id", "version_no", name="uq_module_version_no"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_period"),
    )
    op.create_index(op.f("ix_module_version_tenant_id"), "module_version", ["tenant_id"])
    op.create_index(op.f("ix_module_version_module_id"), "module_version", ["module_id"])
    op.create_index("ix_module_version_module_from", "module_version", ["module_id", "valid_from"])

    op.create_table(
        "module_run", *_common(),
        sa.Column("module_version_id", sa.Uuid(), nullable=False),
        sa.Column("academic_year", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["module_version_id"], ["module_version.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("module_version_id", "academic_year", name="uq_module_run_version_year"),
    )
    op.create_index(op.f("ix_module_run_tenant_id"), "module_run", ["tenant_id"])
    op.create_index(op.f("ix_module_run_module_version_id"), "module_run", ["module_version_id"])

    op.add_column("module_enrolment", sa.Column("module_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_module_enrolment_module_run", "module_enrolment", "module_run",
                          ["module_run_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_module_enrolment_module_run_id"), "module_enrolment", ["module_run_id"])

    if bind.dialect.name != "postgresql":
        return
    enable_rls(_TABLES)

    # Academic-year start (1 Aug) of a date, and of a 'YYYY/YY' label.
    ay_of = ("make_date(CASE WHEN EXTRACT(MONTH FROM {d}) >= 8 THEN CAST(EXTRACT(YEAR FROM {d}) AS INT) "
             "ELSE CAST(EXTRACT(YEAR FROM {d}) AS INT) - 1 END, 8, 1)")
    n_versions = bind.execute(sa.text(f"""
        INSERT INTO module_version (id, tenant_id, module_id, version_no, title, credits, level, term,
                                    valid_from, change_note)
        SELECT gen_random_uuid(), m.tenant_id, m.id, 1, m.title, COALESCE(m.credits, 0),
               COALESCE(m.level, 7), m.term,
               LEAST({ay_of.format(d='m.created_at')},
                     COALESCE((SELECT MIN(make_date(CAST(substr(e.academic_year, 1, 4) AS INT), 8, 1))
                               FROM module_enrolment e
                               WHERE e.module_id = m.id AND e.academic_year ~ '^[0-9]{{4}}'),
                              {ay_of.format(d='m.created_at')})),
               'First version (rebuilt from existing data)'
        FROM taught_module m
        WHERE NOT EXISTS (SELECT 1 FROM module_version v WHERE v.module_id = m.id)
    """)).rowcount
    n_runs = bind.execute(sa.text("""
        INSERT INTO module_run (id, tenant_id, module_version_id, academic_year, start_date, end_date)
        SELECT gen_random_uuid(), v.tenant_id, v.id, y.academic_year,
               CASE WHEN y.academic_year ~ '^[0-9]{4}'
                    THEN make_date(CAST(substr(y.academic_year, 1, 4) AS INT), 8, 1) END,
               CASE WHEN y.academic_year ~ '^[0-9]{4}'
                    THEN make_date(CAST(substr(y.academic_year, 1, 4) AS INT) + 1, 7, 31) END
        FROM (SELECT DISTINCT module_id, academic_year FROM module_enrolment) y
        JOIN module_version v ON v.module_id = y.module_id AND v.version_no = 1
    """)).rowcount
    n_linked = bind.execute(sa.text("""
        UPDATE module_enrolment e SET module_run_id = r.id
        FROM module_run r JOIN module_version v ON v.id = r.module_version_id
        WHERE v.module_id = e.module_id AND r.academic_year = e.academic_year AND e.module_run_id IS NULL
    """)).rowcount
    unlinked = bind.execute(sa.text(
        "SELECT count(*) FROM module_enrolment WHERE module_run_id IS NULL")).scalar()
    log.info("Module versions backfilled: %s versions, %s runs, %s enrolments linked",
             n_versions, n_runs, n_linked)
    if unlinked:
        raise RuntimeError(f"{unlinked} module enrolment(s) could not be linked to a run")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        disable_rls(_TABLES)
    op.drop_index(op.f("ix_module_enrolment_module_run_id"), table_name="module_enrolment")
    op.drop_constraint("fk_module_enrolment_module_run", "module_enrolment", type_="foreignkey")
    op.drop_column("module_enrolment", "module_run_id")
    op.drop_table("module_run")
    op.drop_table("module_version")
