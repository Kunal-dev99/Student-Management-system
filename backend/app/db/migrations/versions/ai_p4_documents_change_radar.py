"""AI-P4 — versioned documents + change findings."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ai_p4_documents_change_radar"
down_revision: Union[str, Sequence[str], None] = "ai_p2_interventions_engagement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_version",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_ref", sa.String(length=300), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=True),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=80), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("extraction_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("extractor_version", sa.String(length=40), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_version_document_ref", "document_version", ["document_ref"])
    op.create_index("ix_document_version_student_id", "document_version", ["student_id"])

    op.create_table(
        "document_chunk",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_heading", sa.String(length=300), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("span_hash", sa.String(length=64), nullable=False),
        sa.Column("text", sa.String(length=8000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["document_version.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_chunk_version_id", "document_chunk", ["version_id"])

    op.create_table(
        "change_finding",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_a_id", sa.Uuid(), nullable=False),
        sa.Column("version_b_id", sa.Uuid(), nullable=False),
        sa.Column("change_type", sa.String(length=60), nullable=False),
        sa.Column("severity_for_review", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("source_a_ref", sa.JSON(), nullable=True),
        sa.Column("source_b_ref", sa.JSON(), nullable=True),
        sa.Column("summary", sa.String(length=1000), nullable=False),
        sa.Column("reviewer_disposition", sa.String(length=20), nullable=True),
        sa.Column("reviewer_note", sa.String(length=1000), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["version_a_id"], ["document_version.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_b_id"], ["document_version.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_change_finding_version_a_id", "change_finding", ["version_a_id"])
    op.create_index("ix_change_finding_version_b_id", "change_finding", ["version_b_id"])
    op.create_index("ix_change_finding_change_type", "change_finding", ["change_type"])


def downgrade() -> None:
    for tbl, idxs in [
        ("change_finding", ["ix_change_finding_change_type",
                             "ix_change_finding_version_b_id",
                             "ix_change_finding_version_a_id"]),
        ("document_chunk", ["ix_document_chunk_version_id"]),
        ("document_version", ["ix_document_version_student_id", "ix_document_version_document_ref"]),
    ]:
        for ix in idxs:
            op.drop_index(ix, table_name=tbl)
        op.drop_table(tbl)
