"""F2 — Person integrity: contacts, merge records, pseudonymised flag.

Adds:
- person.pseudonymised_at (nullable timestamp, marks a GDPR-erased person)
- person_contact (channel, value, verified_at, do_not_contact) with FK to person
- person_merge_record (immutable evidence of a merge)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2_person_gdpr"
down_revision: Union[str, Sequence[str], None] = "f1_signoff_2026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "person",
        sa.Column("pseudonymised_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "person_contact",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column(
            "channel",
            sa.Enum("email", "phone", "mobile", "address", "emergency",
                    name="person_contact_channel"),
            nullable=False,
        ),
        sa.Column("value", sa.String(length=320), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("do_not_contact", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], name=op.f("fk_person_contact_person_id_person"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_person_contact")),
    )
    op.create_index(op.f("ix_person_contact_person_id"), "person_contact", ["person_id"])

    op.create_table(
        "person_merge_record",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("surviving_person_id", sa.Uuid(), nullable=False),
        sa.Column("losing_person_id", sa.Uuid(), nullable=False),
        sa.Column("losing_person_snapshot", sa.JSON(), nullable=True),
        sa.Column("fk_touched", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("merged_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["merged_by_user_id"], ["users.id"],
                                name=op.f("fk_person_merge_record_merged_by_user_id_users"),
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_person_merge_record")),
    )
    op.create_index(op.f("ix_person_merge_record_surviving_person_id"), "person_merge_record", ["surviving_person_id"])
    op.create_index(op.f("ix_person_merge_record_losing_person_id"), "person_merge_record", ["losing_person_id"])
    op.create_index(op.f("ix_person_merge_record_merged_at"), "person_merge_record", ["merged_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_person_merge_record_merged_at"), table_name="person_merge_record")
    op.drop_index(op.f("ix_person_merge_record_losing_person_id"), table_name="person_merge_record")
    op.drop_index(op.f("ix_person_merge_record_surviving_person_id"), table_name="person_merge_record")
    op.drop_table("person_merge_record")
    op.drop_index(op.f("ix_person_contact_person_id"), table_name="person_contact")
    op.drop_table("person_contact")
    sa.Enum(name="person_contact_channel").drop(op.get_bind(), checkfirst=True)
    op.drop_column("person", "pseudonymised_at")
