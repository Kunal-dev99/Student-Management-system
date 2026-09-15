"""ICR G1 - taught (PGT / MSc) student lifecycle.

Additive only:
- programme.programme_type (research [default] / taught) + programme.taught_total_credits.
- New tables: taught_module, module_enrolment, module_assessment, assessment_result,
  dissertation, taught_award.

Nothing existing is dropped or altered in behaviour: every current programme defaults to
'research' and every research code path is untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "icr_g1_taught_lifecycle"
down_revision: Union[str, Sequence[str], None] = "ai_p1_widen_telemetry_cols"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# programme_type is used by op.add_column below, which does not create the type itself, so it is
# created explicitly up front (funding-migration pattern). The other three enums are used only
# inside create_table, which creates the type as part of table creation — so they are NOT
# pre-created here and their columns keep the default create_type=True. .create()/.drop() are
# no-ops on SQLite.
programme_type = sa.Enum("research", "taught", name="programme_type")
assessment_type = sa.Enum(
    "essay", "exam", "coursework", "presentation", "dissertation", name="assessment_type"
)
module_enrolment_status = sa.Enum(
    "enrolled", "completed", "withdrawn", "failed", name="module_enrolment_status"
)
classification_band = sa.Enum(
    "distinction", "merit", "pass", "fail", name="classification_band"
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    programme_type.create(bind, checkfirst=True)

    # --- Programme: type + target credits ---
    op.add_column(
        "programme",
        sa.Column(
            "programme_type",
            sa.Enum("research", "taught", name="programme_type", create_type=False),
            nullable=False,
            server_default="research",
        ),
    )
    op.add_column("programme", sa.Column("taught_total_credits", sa.Integer(), nullable=True))

    # --- taught_module ---
    op.create_table(
        "taught_module",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("programme_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("term", sa.String(length=60), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["programme_id"], ["programme.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_taught_module_programme_id", "taught_module", ["programme_id"])

    # --- module_enrolment ---
    op.create_table(
        "module_enrolment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("academic_year", sa.String(length=20), nullable=False),
        sa.Column("status",
                  sa.Enum("enrolled", "completed", "withdrawn", "failed",
                          name="module_enrolment_status"),
                  nullable=False, server_default="enrolled"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["module_id"], ["taught_module.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_module_enrolment_student_id", "module_enrolment", ["student_id"])
    op.create_index("ix_module_enrolment_module_id", "module_enrolment", ["module_id"])
    op.create_index("ix_module_enrolment_status", "module_enrolment", ["status"])

    # --- module_assessment ---
    op.create_table(
        "module_assessment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("module_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("assessment_type",
                  sa.Enum("essay", "exam", "coursework", "presentation", "dissertation",
                          name="assessment_type"),
                  nullable=False),
        sa.Column("weight_pct", sa.Numeric(precision=5, scale=2),
                  nullable=False, server_default="100.00"),
        sa.Column("max_mark", sa.Numeric(precision=5, scale=2),
                  nullable=False, server_default="100.00"),
        sa.Column("due_date", sa.Date(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["module_id"], ["taught_module.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_module_assessment_module_id", "module_assessment", ["module_id"])

    # --- assessment_result ---
    op.create_table(
        "assessment_result",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("module_enrolment_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("mark", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("grade", sa.String(length=20), nullable=True),
        sa.Column("is_resit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("marked_by_user_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["module_enrolment_id"], ["module_enrolment.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessment_id"], ["module_assessment.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["marked_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assessment_result_module_enrolment_id", "assessment_result", ["module_enrolment_id"])
    op.create_index("ix_assessment_result_assessment_id", "assessment_result", ["assessment_id"])

    # --- dissertation ---
    op.create_table(
        "dissertation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("supervisor_person_id", sa.Uuid(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mark", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("grade", sa.String(length=20), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supervisor_person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", name="uq_dissertation_student_id"),
    )
    op.create_index("ix_dissertation_student_id", "dissertation", ["student_id"])

    # --- taught_award ---
    op.create_table(
        "taught_award",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("final_mark", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("classification",
                  sa.Enum("distinction", "merit", "pass", "fail",
                          name="classification_band"),
                  nullable=True),
        sa.Column("credits_achieved", sa.Integer(), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", name="uq_taught_award_student_id"),
    )
    op.create_index("ix_taught_award_student_id", "taught_award", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_taught_award_student_id", table_name="taught_award")
    op.drop_table("taught_award")
    op.drop_index("ix_dissertation_student_id", table_name="dissertation")
    op.drop_table("dissertation")
    op.drop_index("ix_assessment_result_assessment_id", table_name="assessment_result")
    op.drop_index("ix_assessment_result_module_enrolment_id", table_name="assessment_result")
    op.drop_table("assessment_result")
    op.drop_index("ix_module_assessment_module_id", table_name="module_assessment")
    op.drop_table("module_assessment")
    op.drop_index("ix_module_enrolment_status", table_name="module_enrolment")
    op.drop_index("ix_module_enrolment_module_id", table_name="module_enrolment")
    op.drop_index("ix_module_enrolment_student_id", table_name="module_enrolment")
    op.drop_table("module_enrolment")
    op.drop_index("ix_taught_module_programme_id", table_name="taught_module")
    op.drop_table("taught_module")

    op.drop_column("programme", "taught_total_credits")
    op.drop_column("programme", "programme_type")

    bind = op.get_bind()
    classification_band.drop(bind, checkfirst=True)
    module_enrolment_status.drop(bind, checkfirst=True)
    assessment_type.drop(bind, checkfirst=True)
    programme_type.drop(bind, checkfirst=True)
