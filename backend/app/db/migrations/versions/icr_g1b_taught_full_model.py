"""ICR G1 (full academic model) - deepen the taught lifecycle.

Additive columns only + one new enum (module_outcome). Existing taught rows get sensible
server defaults, so nothing breaks:
- taught_module: level (7), is_core (true), convenor_person_id
- module_assessment: pass_mark (50), resit_allowed (true), resit_cap
- assessment_result: attempt_number (1), capped (false)
- module_enrolment: final_mark, outcome (pending), credits_awarded, condoned (false)
- dissertation: second_marker_person_id, first_mark, second_mark, word_count
- programme: grading_policy (JSON)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "icr_g1b_taught_full_model"
down_revision: Union[str, Sequence[str], None] = "icr_g4_study_intensity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


module_outcome = sa.Enum("pending", "passed", "condoned", "failed", name="module_outcome")


def upgrade() -> None:
    bind = op.get_bind()
    module_outcome.create(bind, checkfirst=True)

    # taught_module
    op.add_column("taught_module", sa.Column("level", sa.Integer(), nullable=False, server_default="7"))
    op.add_column("taught_module", sa.Column("is_core", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("taught_module", sa.Column("convenor_person_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_taught_module_convenor", "taught_module", "person", ["convenor_person_id"], ["id"]
    )

    # module_assessment
    op.add_column("module_assessment", sa.Column("pass_mark", sa.Numeric(5, 2), nullable=False, server_default="50.00"))
    op.add_column("module_assessment", sa.Column("resit_allowed", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("module_assessment", sa.Column("resit_cap", sa.Numeric(5, 2), nullable=True))

    # assessment_result
    op.add_column("assessment_result", sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("assessment_result", sa.Column("capped", sa.Boolean(), nullable=False, server_default=sa.false()))

    # module_enrolment
    op.add_column("module_enrolment", sa.Column("final_mark", sa.Numeric(5, 2), nullable=True))
    op.add_column(
        "module_enrolment",
        sa.Column("outcome",
                  sa.Enum("pending", "passed", "condoned", "failed", name="module_outcome", create_type=False),
                  nullable=False, server_default="pending"),
    )
    op.add_column("module_enrolment", sa.Column("credits_awarded", sa.Integer(), nullable=True))
    op.add_column("module_enrolment", sa.Column("condoned", sa.Boolean(), nullable=False, server_default=sa.false()))

    # dissertation
    op.add_column("dissertation", sa.Column("second_marker_person_id", sa.Uuid(), nullable=True))
    op.add_column("dissertation", sa.Column("first_mark", sa.Numeric(5, 2), nullable=True))
    op.add_column("dissertation", sa.Column("second_mark", sa.Numeric(5, 2), nullable=True))
    op.add_column("dissertation", sa.Column("word_count", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_dissertation_second_marker", "dissertation", "person", ["second_marker_person_id"], ["id"]
    )

    # programme
    op.add_column("programme", sa.Column("grading_policy", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("programme", "grading_policy")
    op.drop_constraint("fk_dissertation_second_marker", "dissertation", type_="foreignkey")
    op.drop_column("dissertation", "word_count")
    op.drop_column("dissertation", "second_mark")
    op.drop_column("dissertation", "first_mark")
    op.drop_column("dissertation", "second_marker_person_id")
    op.drop_column("module_enrolment", "condoned")
    op.drop_column("module_enrolment", "credits_awarded")
    op.drop_column("module_enrolment", "outcome")
    op.drop_column("module_enrolment", "final_mark")
    op.drop_column("assessment_result", "capped")
    op.drop_column("assessment_result", "attempt_number")
    op.drop_column("module_assessment", "resit_cap")
    op.drop_column("module_assessment", "resit_allowed")
    op.drop_column("module_assessment", "pass_mark")
    op.drop_constraint("fk_taught_module_convenor", "taught_module", type_="foreignkey")
    op.drop_column("taught_module", "convenor_person_id")
    op.drop_column("taught_module", "is_core")
    op.drop_column("taught_module", "level")
    module_outcome.drop(op.get_bind(), checkfirst=True)
