"""CB-C — Assistant unmatched-query telemetry table."""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "cb_assistant_vocab_review"
down_revision: Union[str, Sequence[str], None] = "w2_supervisor_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_unmatched_query",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("query_redacted", sa.Text(), nullable=False),
        sa.Column("original_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("session_role", sa.String(80), nullable=True),
        sa.Column("suggested_intents", sa.JSON(), nullable=True),
        sa.Column("assigned_intent", sa.String(120), nullable=True),
        sa.Column("synonym_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_assistant_unmatched_query_assigned_intent",
        "assistant_unmatched_query", ["assigned_intent"],
    )
    op.create_index(
        "ix_assistant_unmatched_query_created_at",
        "assistant_unmatched_query", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_assistant_unmatched_query_created_at",
                  table_name="assistant_unmatched_query")
    op.drop_index("ix_assistant_unmatched_query_assigned_intent",
                  table_name="assistant_unmatched_query")
    op.drop_table("assistant_unmatched_query")
