"""F3 — Recruitment depth: references, interviews, offer conditions, fee-status / visa on Application.

Adds:
- application.fee_status / visa_required / visa_check_completed_at
- reference_request
- interview + interview_panellist
- offer_condition
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f3_recruitment_depth"
down_revision: Union[str, Sequence[str], None] = "f2_person_gdpr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fee():   return postgresql.ENUM("home", "overseas", "channel_islands", "unknown", name="fee_status", create_type=False)
def _ref():   return postgresql.ENUM("requested", "received", "declined", "expired", name="reference_request_status", create_type=False)
def _ivst():  return postgresql.ENUM("scheduled", "completed", "cancelled", name="interview_status", create_type=False)
def _ivout(): return postgresql.ENUM("unrecorded", "proceed", "hold", "reject", name="interview_outcome", create_type=False)
def _cond():  return postgresql.ENUM("pending", "satisfied", "waived", name="offer_condition_status", create_type=False)


def upgrade() -> None:
    # Create every enum type exactly once, up front, via raw SQL — asyncpg's create_type=False on
    # sa.Enum still tries to emit CREATE TYPE inside create_table on this driver, so we bypass it.
    op.execute("CREATE TYPE fee_status AS ENUM ('home','overseas','channel_islands','unknown')")
    op.execute("CREATE TYPE reference_request_status AS ENUM ('requested','received','declined','expired')")
    op.execute("CREATE TYPE interview_status AS ENUM ('scheduled','completed','cancelled')")
    op.execute("CREATE TYPE interview_outcome AS ENUM ('unrecorded','proceed','hold','reject')")
    op.execute("CREATE TYPE offer_condition_status AS ENUM ('pending','satisfied','waived')")

    op.add_column("application",
        sa.Column("fee_status", _fee(), nullable=False, server_default="unknown"))
    op.add_column("application",
        sa.Column("visa_required", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("application",
        sa.Column("visa_check_completed_at", sa.DateTime(timezone=True), nullable=True))

    # reference_request
    op.create_table(
        "reference_request",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("referee_name", sa.String(length=200), nullable=False),
        sa.Column("referee_email", sa.String(length=320), nullable=False),
        sa.Column("referee_affiliation", sa.String(length=300), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", _ref(), nullable=False, server_default="requested"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("response_document_ref", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"],
                                name=op.f("fk_reference_request_application_id_application"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reference_request")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_reference_request_token_hash")),
    )
    op.create_index(op.f("ix_reference_request_application_id"), "reference_request", ["application_id"])
    op.create_index(op.f("ix_reference_request_token_hash"), "reference_request", ["token_hash"])

    # interview + interview_panellist
    op.create_table(
        "interview",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(length=300), nullable=True),
        sa.Column("status", _ivst(), nullable=False, server_default="scheduled"),
        sa.Column("outcome", _ivout(), nullable=False, server_default="unrecorded"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["application.id"],
                                name=op.f("fk_interview_application_id_application"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview")),
    )
    op.create_index(op.f("ix_interview_application_id"), "interview", ["application_id"])

    op.create_table(
        "interview_panellist",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["interview_id"], ["interview.id"],
                                name=op.f("fk_interview_panellist_interview_id_interview"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"],
                                name=op.f("fk_interview_panellist_person_id_person")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_panellist")),
    )
    op.create_index(op.f("ix_interview_panellist_interview_id"), "interview_panellist", ["interview_id"])
    op.create_index(op.f("ix_interview_panellist_person_id"), "interview_panellist", ["person_id"])
    op.create_index("uq_interview_panellist", "interview_panellist", ["interview_id", "person_id"], unique=True)

    # offer_condition
    op.create_table(
        "offer_condition",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("offer_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("satisfy_by", sa.Date(), nullable=True),
        sa.Column("status", _cond(), nullable=False, server_default="pending"),
        sa.Column("satisfied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_document_ref", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["offer_id"], ["offer.id"],
                                name=op.f("fk_offer_condition_offer_id_offer"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer_condition")),
    )
    op.create_index(op.f("ix_offer_condition_offer_id"), "offer_condition", ["offer_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_offer_condition_offer_id"), table_name="offer_condition")
    op.drop_table("offer_condition")
    op.execute("DROP TYPE IF EXISTS offer_condition_status")

    op.drop_index("uq_interview_panellist", table_name="interview_panellist")
    op.drop_index(op.f("ix_interview_panellist_person_id"), table_name="interview_panellist")
    op.drop_index(op.f("ix_interview_panellist_interview_id"), table_name="interview_panellist")
    op.drop_table("interview_panellist")

    op.drop_index(op.f("ix_interview_application_id"), table_name="interview")
    op.drop_table("interview")
    op.execute("DROP TYPE IF EXISTS interview_outcome")
    op.execute("DROP TYPE IF EXISTS interview_status")

    op.drop_index(op.f("ix_reference_request_token_hash"), table_name="reference_request")
    op.drop_index(op.f("ix_reference_request_application_id"), table_name="reference_request")
    op.drop_table("reference_request")
    op.execute("DROP TYPE IF EXISTS reference_request_status")

    op.drop_column("application", "visa_check_completed_at")
    op.drop_column("application", "visa_required")
    op.drop_column("application", "fee_status")
    op.execute("DROP TYPE IF EXISTS fee_status")
