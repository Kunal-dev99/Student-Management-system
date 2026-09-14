"""AI-P2 — Interventions, supervision commitments, engagement trajectory."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ai_p2_interventions_engagement"
down_revision: Union[str, Sequence[str], None] = "ai_p1_intelligence_foundations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intervention_plan",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_ref", sa.String(length=120), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=True),
        sa.Column("rationale", sa.String(length=2000), nullable=False),
        sa.Column("source_signal", sa.JSON(), nullable=True),
        sa.Column("reassess_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_intervention_plan_idempotency"),
    )
    op.create_index("ix_intervention_plan_case_ref", "intervention_plan", ["case_ref"])
    op.create_index("ix_intervention_plan_student_id", "intervention_plan", ["student_id"])
    op.create_index("ix_intervention_plan_status", "intervention_plan", ["status"])

    op.create_table(
        "intervention_action",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=60), nullable=False),
        sa.Column("target_ref", sa.JSON(), nullable=False),
        sa.Column("owner_ref", sa.JSON(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_ref", sa.JSON(), nullable=True),
        sa.Column("error_reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["intervention_plan.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "idempotency_key",
                             name="uq_intervention_action_plan_idem"),
    )
    op.create_index("ix_intervention_action_plan_id", "intervention_action", ["plan_id"])
    op.create_index("ix_intervention_action_action_type", "intervention_action", ["action_type"])
    op.create_index("ix_intervention_action_status", "intervention_action", ["status"])

    op.create_table(
        "intervention_outcome",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=False),
        sa.Column("after_state", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["intervention_plan.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_intervention_outcome_plan_id", "intervention_outcome", ["plan_id"])

    op.create_table(
        "supervision_commitment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column("owner_person_or_role", sa.String(length=120), nullable=True),
        sa.Column("dependency_ids", sa.JSON(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("evidence_link", sa.JSON(), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["supervision_meeting.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_supervision_commitment_meeting_id", "supervision_commitment", ["meeting_id"])
    op.create_index("ix_supervision_commitment_student_id", "supervision_commitment", ["student_id"])
    op.create_index("ix_supervision_commitment_status", "supervision_commitment", ["status"])

    op.create_table(
        "engagement_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_engagement_event_student_id", "engagement_event", ["student_id"])
    op.create_index("ix_engagement_event_occurred_at", "engagement_event", ["occurred_at"])
    op.create_index("ix_engagement_event_kind", "engagement_event", ["kind"])

    op.create_table(
        "engagement_snapshot",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("label", sa.String(length=30), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("drivers", sa.JSON(), nullable=True),
        sa.Column("engine", sa.String(length=20), nullable=False, server_default="rules"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "computed_at",
                             name="uq_engagement_snapshot_student_computed"),
    )
    op.create_index("ix_engagement_snapshot_student_id", "engagement_snapshot", ["student_id"])
    op.create_index("ix_engagement_snapshot_computed_at", "engagement_snapshot", ["computed_at"])


def downgrade() -> None:
    for tbl, idxs in [
        ("engagement_snapshot", ["ix_engagement_snapshot_computed_at", "ix_engagement_snapshot_student_id"]),
        ("engagement_event", ["ix_engagement_event_kind", "ix_engagement_event_occurred_at", "ix_engagement_event_student_id"]),
        ("supervision_commitment", ["ix_supervision_commitment_status", "ix_supervision_commitment_student_id", "ix_supervision_commitment_meeting_id"]),
        ("intervention_outcome", ["ix_intervention_outcome_plan_id"]),
        ("intervention_action", ["ix_intervention_action_status", "ix_intervention_action_action_type", "ix_intervention_action_plan_id"]),
        ("intervention_plan", ["ix_intervention_plan_status", "ix_intervention_plan_student_id", "ix_intervention_plan_case_ref"]),
    ]:
        for ix in idxs:
            op.drop_index(ix, table_name=tbl)
        op.drop_table(tbl)
