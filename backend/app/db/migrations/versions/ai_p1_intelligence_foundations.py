"""AI-P1 — Intelligence foundations (Evidence, Prediction snapshots, Telemetry).

Adds four append-mostly tables the intelligence layer needs. Deleting these leaves
domain data intact — the tables carry derived data, never source-of-truth state.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ai_p1_intelligence_foundations"
down_revision: Union[str, Sequence[str], None] = "cost_centre_project_code_lov"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evidence_claim",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("artefact_id", sa.Uuid(), nullable=False),
        sa.Column("claim_type", sa.String(length=40), nullable=False),
        sa.Column("source_type", sa.String(length=60), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=True),
        sa.Column("locator", sa.JSON(), nullable=True),
        sa.Column("value_hash", sa.String(length=64), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("permission_scope", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="verified"),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_claim_artefact_id", "evidence_claim", ["artefact_id"])
    op.create_index("ix_evidence_claim_claim_type", "evidence_claim", ["claim_type"])

    op.create_table(
        "prediction_snapshot",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("target", sa.String(length=80), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("predicted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("model_health", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_version_id"], ["ml_model_version.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "model_version_id", "predicted_at",
                             name="uq_prediction_snapshot_student_model_time"),
    )
    op.create_index("ix_prediction_snapshot_student_id", "prediction_snapshot", ["student_id"])
    op.create_index("ix_prediction_snapshot_target", "prediction_snapshot", ["target"])
    op.create_index("ix_prediction_snapshot_predicted_at", "prediction_snapshot", ["predicted_at"])

    op.create_table(
        "driver_snapshot",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("prediction_id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.String(length=40), nullable=False),
        sa.Column("feature", sa.String(length=120), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("delta_pp_or_sensitivity", sa.Float(), nullable=True),
        sa.Column("baseline_value", sa.String(length=120), nullable=True),
        sa.Column("input_value", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["prediction_id"], ["prediction_snapshot.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_driver_snapshot_prediction_id", "driver_snapshot", ["prediction_id"])

    op.create_table(
        "intelligence_telemetry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("call_class", sa.String(length=20), nullable=False),
        sa.Column("feature", sa.String(length=80), nullable=False),
        sa.Column("engine_used", sa.String(length=30), nullable=False),
        sa.Column("fallback_path", sa.String(length=60), nullable=True),
        sa.Column("prompt_template_version", sa.String(length=40), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("cost_estimate_usd", sa.Float(), nullable=True),
        sa.Column("schema_ok", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("principal_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_intelligence_telemetry_call_class", "intelligence_telemetry", ["call_class"])
    op.create_index("ix_intelligence_telemetry_feature", "intelligence_telemetry", ["feature"])
    op.create_index("ix_intelligence_telemetry_request_id", "intelligence_telemetry", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_intelligence_telemetry_request_id", table_name="intelligence_telemetry")
    op.drop_index("ix_intelligence_telemetry_feature", table_name="intelligence_telemetry")
    op.drop_index("ix_intelligence_telemetry_call_class", table_name="intelligence_telemetry")
    op.drop_table("intelligence_telemetry")

    op.drop_index("ix_driver_snapshot_prediction_id", table_name="driver_snapshot")
    op.drop_table("driver_snapshot")

    op.drop_index("ix_prediction_snapshot_predicted_at", table_name="prediction_snapshot")
    op.drop_index("ix_prediction_snapshot_target", table_name="prediction_snapshot")
    op.drop_index("ix_prediction_snapshot_student_id", table_name="prediction_snapshot")
    op.drop_table("prediction_snapshot")

    op.drop_index("ix_evidence_claim_claim_type", table_name="evidence_claim")
    op.drop_index("ix_evidence_claim_artefact_id", table_name="evidence_claim")
    op.drop_table("evidence_claim")
