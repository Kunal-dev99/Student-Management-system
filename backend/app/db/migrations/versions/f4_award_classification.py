"""F4 — Award classification workflow + certificate document link.

Adds to ``award``:
- classification (String)
- classification_state (String, default 'draft')
- proposed_by_user_id / confirmed_by_user_id (FK → users)
- published_at (timestamp)
- certificate_document_id (FK → document)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4_award_classification"
down_revision: Union[str, Sequence[str], None] = "f3_recruitment_depth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("award", sa.Column("classification", sa.String(length=60), nullable=True))
    op.add_column("award",
        sa.Column("classification_state", sa.String(length=20), nullable=False, server_default="draft"))
    op.add_column("award", sa.Column("proposed_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("award", sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True))
    op.add_column("award", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("award", sa.Column("certificate_document_id", sa.Uuid(), nullable=True))
    with op.batch_alter_table("award") as batch:
        batch.create_foreign_key("fk_award_proposed_by_user_id_users", "users",
                                 ["proposed_by_user_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_award_confirmed_by_user_id_users", "users",
                                 ["confirmed_by_user_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_award_certificate_document_id_document", "document",
                                 ["certificate_document_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("award") as batch:
        batch.drop_constraint("fk_award_certificate_document_id_document", type_="foreignkey")
        batch.drop_constraint("fk_award_confirmed_by_user_id_users", type_="foreignkey")
        batch.drop_constraint("fk_award_proposed_by_user_id_users", type_="foreignkey")
    op.drop_column("award", "certificate_document_id")
    op.drop_column("award", "published_at")
    op.drop_column("award", "confirmed_by_user_id")
    op.drop_column("award", "proposed_by_user_id")
    op.drop_column("award", "classification_state")
    op.drop_column("award", "classification")
