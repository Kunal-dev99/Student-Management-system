"""Portal messages — student ↔ supervisor messaging."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "portal_messages"
# Merge-migration: this new table + close out the two open heads (cmp1_composer_run and
# w2_supervisor_profile / cb_assistant_vocab_review). Everything downstream of here has a
# single head to target.
down_revision: Union[str, Sequence[str], None] = ("cmp1_composer_run", "cb_assistant_vocab_review")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portal_message",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("supervisor_person_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("author_role", sa.String(length=20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supervisor_person_id"], ["person.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_portal_message_student_id", "portal_message", ["student_id"])
    op.create_index("ix_portal_message_supervisor_person_id",
                    "portal_message", ["supervisor_person_id"])
    op.create_index("ix_portal_message_thread",
                    "portal_message", ["student_id", "supervisor_person_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_portal_message_thread", table_name="portal_message")
    op.drop_index("ix_portal_message_supervisor_person_id", table_name="portal_message")
    op.drop_index("ix_portal_message_student_id", table_name="portal_message")
    op.drop_table("portal_message")
