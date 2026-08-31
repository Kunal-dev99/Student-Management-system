"""W2 — SupervisorProfile + assignment-request workflow."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "w2_supervisor_profile"
down_revision: Union[str, Sequence[str], None] = "w1_domain_polish"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    pg = bind.dialect.name == "postgresql"

    if pg:
        op.execute(
            "CREATE TYPE supervisor_availability AS ENUM ('available','full','on_leave')"
        )
        op.execute(
            "CREATE TYPE assignment_request_state AS ENUM "
            "('recommended','requested','academic_review','approved','rejected','withdrawn')"
        )

    op.create_table(
        "supervisor_profile",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("max_students", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("availability",
            postgresql.ENUM("available", "full", "on_leave",
                            name="supervisor_availability", create_type=False),
            nullable=False, server_default="available"),
        sa.Column("accepting_new", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sabbatical_from", sa.Date(), nullable=True),
        sa.Column("sabbatical_to", sa.Date(), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"],
                                name=op.f("fk_supervisor_profile_person_id_person"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_supervisor_profile")),
        sa.UniqueConstraint("person_id", name=op.f("uq_supervisor_profile_person_id")),
    )
    op.create_index(op.f("ix_supervisor_profile_person_id"), "supervisor_profile", ["person_id"])
    op.create_index(op.f("ix_supervisor_profile_availability"),
                    "supervisor_profile", ["availability"])

    op.create_table(
        "supervisor_profile_area",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("supervisor_profile_id", sa.Uuid(), nullable=False),
        sa.Column("research_area_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["supervisor_profile_id"], ["supervisor_profile.id"],
                                name=op.f("fk_supervisor_profile_area_supervisor_profile_id_supervisor_profile"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["research_area_id"], ["research_area.id"],
                                name=op.f("fk_supervisor_profile_area_research_area_id_research_area"),
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_supervisor_profile_area")),
    )
    op.create_index(op.f("ix_supervisor_profile_area_supervisor_profile_id"),
                    "supervisor_profile_area", ["supervisor_profile_id"])
    op.create_index(op.f("ix_supervisor_profile_area_research_area_id"),
                    "supervisor_profile_area", ["research_area_id"])

    op.create_table(
        "supervisor_assignment_request",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_supervisor_person_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_role",
            postgresql.ENUM("primary", "co_supervisor", name="supervisor_role", create_type=False),
            nullable=False, server_default="primary"),
        sa.Column("state",
            postgresql.ENUM("recommended", "requested", "academic_review",
                            "approved", "rejected", "withdrawn",
                            name="assignment_request_state", create_type=False),
            nullable=False, server_default="requested"),
        sa.Column("match_score", sa.Integer(), nullable=True),
        sa.Column("match_reasons", sa.JSON(), nullable=True),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"],
                                name=op.f("fk_supervisor_assignment_request_student_id_student"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposed_supervisor_person_id"], ["person.id"],
                                name=op.f("fk_supervisor_assignment_request_proposed_supervisor_person_id_person"),
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"],
                                name=op.f("fk_supervisor_assignment_request_requested_by_user_id_users"),
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"],
                                name=op.f("fk_supervisor_assignment_request_reviewed_by_user_id_users"),
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"],
                                name=op.f("fk_supervisor_assignment_request_decided_by_user_id_users"),
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_supervisor_assignment_request")),
    )
    op.create_index(op.f("ix_supervisor_assignment_request_student_id"),
                    "supervisor_assignment_request", ["student_id"])
    op.create_index(op.f("ix_supervisor_assignment_request_proposed_supervisor_person_id"),
                    "supervisor_assignment_request", ["proposed_supervisor_person_id"])
    op.create_index(op.f("ix_supervisor_assignment_request_state"),
                    "supervisor_assignment_request", ["state"])


def downgrade() -> None:
    op.drop_index(op.f("ix_supervisor_assignment_request_state"),
                  table_name="supervisor_assignment_request")
    op.drop_index(op.f("ix_supervisor_assignment_request_proposed_supervisor_person_id"),
                  table_name="supervisor_assignment_request")
    op.drop_index(op.f("ix_supervisor_assignment_request_student_id"),
                  table_name="supervisor_assignment_request")
    op.drop_table("supervisor_assignment_request")

    op.drop_index(op.f("ix_supervisor_profile_area_research_area_id"), table_name="supervisor_profile_area")
    op.drop_index(op.f("ix_supervisor_profile_area_supervisor_profile_id"), table_name="supervisor_profile_area")
    op.drop_table("supervisor_profile_area")

    op.drop_index(op.f("ix_supervisor_profile_availability"), table_name="supervisor_profile")
    op.drop_index(op.f("ix_supervisor_profile_person_id"), table_name="supervisor_profile")
    op.drop_table("supervisor_profile")

    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS assignment_request_state")
        op.execute("DROP TYPE IF EXISTS supervisor_availability")
