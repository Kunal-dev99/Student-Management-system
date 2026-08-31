"""F6 — Assistant write intents + notification hygiene (quiet hours, email bounces)."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6_assistant_notif"
down_revision: Union[str, Sequence[str], None] = "f5_task_sla"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # notification_preference — quiet hours
    op.add_column("notification_preference", sa.Column("quiet_start", sa.Integer(), nullable=True))
    op.add_column("notification_preference", sa.Column("quiet_end", sa.Integer(), nullable=True))

    # email_bounce
    op.create_table(
        "email_bounce",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("bounce_type", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"],
                                name=op.f("fk_email_bounce_person_id_person"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_bounce")),
    )
    op.create_index(op.f("ix_email_bounce_person_id"), "email_bounce", ["person_id"])
    op.create_index(op.f("ix_email_bounce_email"), "email_bounce", ["email"])

    # assistant_write_intent
    op.create_table(
        "assistant_write_intent",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("preview", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="proposed"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["proposed_by_user_id"], ["users.id"],
                                name=op.f("fk_assistant_write_intent_proposed_by_user_id_users"),
                                ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_write_intent")),
    )
    op.create_index(op.f("ix_assistant_write_intent_proposed_by_user_id"),
                    "assistant_write_intent", ["proposed_by_user_id"])
    op.create_index(op.f("ix_assistant_write_intent_action"),
                    "assistant_write_intent", ["action"])


def downgrade() -> None:
    op.drop_index(op.f("ix_assistant_write_intent_action"), table_name="assistant_write_intent")
    op.drop_index(op.f("ix_assistant_write_intent_proposed_by_user_id"), table_name="assistant_write_intent")
    op.drop_table("assistant_write_intent")
    op.drop_index(op.f("ix_email_bounce_email"), table_name="email_bounce")
    op.drop_index(op.f("ix_email_bounce_person_id"), table_name="email_bounce")
    op.drop_table("email_bounce")
    op.drop_column("notification_preference", "quiet_end")
    op.drop_column("notification_preference", "quiet_start")
