"""F1 — statutory truth: report_profile sign-off columns.

Adds signed_off_by / signed_off_at / signed_off_notes to report_profile. Sign-off is a functional
gate — an owner (Registry / HESA SME) attests that the mappings satisfy the return's mandatory
spec — after which the profile is immutable until unsigned.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1_signoff_2026"
# Merges the two pre-existing heads (800191647194 = Phase 8 settings; 44faaad53ffb = PL5 predictions)
# while adding the sign-off columns. Alembic accepts a tuple of parents for a merge revision.
down_revision: Union[str, Sequence[str], None] = ("800191647194", "44faaad53ffb")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "report_profile",
        sa.Column("signed_off_by", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "report_profile",
        sa.Column("signed_off_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "report_profile",
        sa.Column("signed_off_notes", sa.Text(), nullable=True),
    )
    # Named FK for portability; users table already exists.
    with op.batch_alter_table("report_profile") as batch:
        batch.create_foreign_key(
            "fk_report_profile_signed_off_by_users",
            "users",
            ["signed_off_by"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("report_profile") as batch:
        batch.drop_constraint("fk_report_profile_signed_off_by_users", type_="foreignkey")
    op.drop_column("report_profile", "signed_off_notes")
    op.drop_column("report_profile", "signed_off_at")
    op.drop_column("report_profile", "signed_off_by")
