"""AI-P6 — Policy Compiler tables (policy_version, policy_proposal)."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ai_p6_policy_compiler"
down_revision: Union[str, Sequence[str], None] = "ai_p4_documents_change_radar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_version",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("policy_ref", sa.String(length=120), nullable=False),
        sa.Column("version_label", sa.String(length=60), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_version.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policy_version_policy_ref", "policy_version", ["policy_ref"])

    op.create_table(
        "policy_proposal",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_version_id", sa.Uuid(), nullable=False),
        sa.Column("rule_candidates", sa.JSON(), nullable=True),
        sa.Column("config_candidates", sa.JSON(), nullable=True),
        sa.Column("simulation_result", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_version_id"], ["policy_version.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policy_proposal_source_version_id", "policy_proposal", ["source_version_id"])


def downgrade() -> None:
    op.drop_index("ix_policy_proposal_source_version_id", table_name="policy_proposal")
    op.drop_table("policy_proposal")
    op.drop_index("ix_policy_version_policy_ref", table_name="policy_version")
    op.drop_table("policy_version")
