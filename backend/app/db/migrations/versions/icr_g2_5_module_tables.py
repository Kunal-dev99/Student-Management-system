"""ICR gaps 2-5 — ICR module-owned tables.

Adds:
- icr_clinical_placement (gap 2)
- icr_independent_tutor + icr_independent_tutor_note (gap 3)
- icr_bench_fee_allocation + icr_bench_fee_drawdown (gap 4)
- icr_partner_affiliation (gap 5)
- person_relationship_type enum value 'clinical_trainee' (gap 2)

All additive; every table hangs off ``student.id`` with ``ON DELETE CASCADE``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "icr_g25_tables"
down_revision: Union[str, Sequence[str], None] = "icr_g1_reg_flip"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # New enum value for the concurrent identity (gap 2). Postgres-only DDL — SQLite renders enums
    # as VARCHAR + CHECK, so this migration is a no-op on the test database (create_all suffices).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE person_relationship_type ADD VALUE IF NOT EXISTS 'clinical_trainee'")

    # Gap 2 — clinical placements
    op.create_table(
        "icr_clinical_placement",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("trust_name", sa.String(length=200), nullable=False),
        sa.Column("specialty", sa.String(length=120), nullable=False),
        sa.Column("grade", sa.String(length=60), nullable=False),
        sa.Column("supervisor_name", sa.String(length=200), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("sessions_per_week", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"],
                                name=op.f("fk_icr_clinical_placement_student_id_student"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_icr_clinical_placement")),
    )
    op.create_index(op.f("ix_icr_clinical_placement_student_id"), "icr_clinical_placement", ["student_id"])

    # Gap 3 — independent tutor + private notes
    op.create_table(
        "icr_independent_tutor",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("tutor_person_id", sa.Uuid(), nullable=False),
        sa.Column("tutor_department_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"],
                                name=op.f("fk_icr_independent_tutor_student_id_student"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tutor_person_id"], ["person.id"],
                                name=op.f("fk_icr_independent_tutor_tutor_person_id_person"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tutor_department_id"], ["department.id"],
                                name=op.f("fk_icr_independent_tutor_tutor_department_id_department"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_icr_independent_tutor")),
    )
    op.create_index(op.f("ix_icr_independent_tutor_student_id"), "icr_independent_tutor", ["student_id"])
    op.create_index(op.f("ix_icr_independent_tutor_tutor_person_id"), "icr_independent_tutor", ["tutor_person_id"])
    op.create_index("uq_icr_independent_tutor_current", "icr_independent_tutor",
                    ["student_id", "tutor_person_id", "ended_at"])

    op.create_table(
        "icr_independent_tutor_note",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tutor_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("authored_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("authored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tutor_id"], ["icr_independent_tutor.id"],
                                name=op.f("fk_icr_independent_tutor_note_tutor_id_icr_independent_tutor"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["authored_by_user_id"], ["users.id"],
                                name=op.f("fk_icr_independent_tutor_note_authored_by_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_icr_independent_tutor_note")),
    )
    op.create_index(op.f("ix_icr_independent_tutor_note_tutor_id"), "icr_independent_tutor_note", ["tutor_id"])

    # Gap 4 — bench fees
    op.create_table(
        "icr_bench_fee_allocation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("funding_source_id", sa.Uuid(), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="GBP"),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("cost_centre", sa.String(length=60), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"],
                                name=op.f("fk_icr_bench_fee_allocation_student_id_student"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["funding_source_id"], ["funding_source.id"],
                                name=op.f("fk_icr_bench_fee_allocation_funding_source_id_funding_source"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_icr_bench_fee_allocation")),
    )
    op.create_index(op.f("ix_icr_bench_fee_allocation_student_id"), "icr_bench_fee_allocation", ["student_id"])

    op.create_table(
        "icr_bench_fee_drawdown",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("allocation_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("drawn_at", sa.Date(), nullable=False),
        sa.Column("invoice_ref", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["allocation_id"], ["icr_bench_fee_allocation.id"],
                                name=op.f("fk_icr_bench_fee_drawdown_allocation_id_icr_bench_fee_allocation"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_icr_bench_fee_drawdown")),
    )
    op.create_index(op.f("ix_icr_bench_fee_drawdown_allocation_id"), "icr_bench_fee_drawdown", ["allocation_id"])

    # Gap 5 — partner affiliations
    op.create_table(
        "icr_partner_affiliation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("partner_name", sa.String(length=200), nullable=False),
        sa.Column("affiliation_kind", sa.String(length=60), nullable=False),
        sa.Column("partner_ref", sa.String(length=120), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("compliance", sa.JSON(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"],
                                name=op.f("fk_icr_partner_affiliation_student_id_student"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_icr_partner_affiliation")),
    )
    op.create_index(op.f("ix_icr_partner_affiliation_student_id"), "icr_partner_affiliation", ["student_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_icr_partner_affiliation_student_id"), table_name="icr_partner_affiliation")
    op.drop_table("icr_partner_affiliation")
    op.drop_index(op.f("ix_icr_bench_fee_drawdown_allocation_id"), table_name="icr_bench_fee_drawdown")
    op.drop_table("icr_bench_fee_drawdown")
    op.drop_index(op.f("ix_icr_bench_fee_allocation_student_id"), table_name="icr_bench_fee_allocation")
    op.drop_table("icr_bench_fee_allocation")
    op.drop_index(op.f("ix_icr_independent_tutor_note_tutor_id"), table_name="icr_independent_tutor_note")
    op.drop_table("icr_independent_tutor_note")
    op.drop_index("uq_icr_independent_tutor_current", table_name="icr_independent_tutor")
    op.drop_index(op.f("ix_icr_independent_tutor_tutor_person_id"), table_name="icr_independent_tutor")
    op.drop_index(op.f("ix_icr_independent_tutor_student_id"), table_name="icr_independent_tutor")
    op.drop_table("icr_independent_tutor")
    op.drop_index(op.f("ix_icr_clinical_placement_student_id"), table_name="icr_clinical_placement")
    op.drop_table("icr_clinical_placement")
    # Postgres does not support removing enum values in a downgrade — leave 'clinical_trainee' in place.
