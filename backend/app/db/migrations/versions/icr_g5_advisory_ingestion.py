"""ICR G5 - statutory advisory ingestion.

Two new tables, additive (no changes to existing tables):
- statutory_advisory: an ingested advisory + its deterministic diff (changes/proposed pack)
- statutory_spec_version: the DB-backed accepted spec-pack versions the resolver overlays
Two new enums: advisory_status, spec_version_status.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "icr_g5_advisory_ingestion"
down_revision: Union[str, Sequence[str], None] = "icr_g1b_taught_full_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Each enum is used by exactly one table, so we let create_table own its CREATE TYPE (create_type
# default True). An explicit .create(checkfirst=True) alongside a column enum double-emitted the
# type under asyncpg, so we deliberately do not pre-create here.
advisory_status = sa.Enum("ingested", "accepted", "rejected", name="advisory_status")
spec_version_status = sa.Enum("active", "superseded", name="spec_version_status")


def upgrade() -> None:
    op.create_table(
        "statutory_advisory",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("pack_code", sa.String(length=40), nullable=False),
        sa.Column("academic_year", sa.String(length=9), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="paste"),
        sa.Column("status", advisory_status, nullable=False, server_default="ingested"),
        sa.Column("base_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parse_source", sa.String(length=20), nullable=False, server_default="directive"),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("proposed_fields", sa.JSON(), nullable=True),
        sa.Column("proposed_rules", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_statutory_advisory_pack_code", "statutory_advisory", ["pack_code"])
    op.create_index("ix_statutory_advisory_academic_year", "statutory_advisory", ["academic_year"])
    op.create_index("ix_statutory_advisory_status", "statutory_advisory", ["status"])

    op.create_table(
        "statutory_spec_version",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("pack_code", sa.String(length=40), nullable=False),
        sa.Column("academic_year", sa.String(length=9), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", spec_version_status, nullable=False, server_default="active"),
        sa.Column("fields", sa.JSON(), nullable=True),
        sa.Column("rules", sa.JSON(), nullable=True),
        sa.Column("source_advisory_id", sa.Uuid(), nullable=True),
        sa.Column("accepted_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_advisory_id"], ["statutory_advisory.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["accepted_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_statutory_spec_version_pack_code", "statutory_spec_version", ["pack_code"])
    op.create_index("ix_statutory_spec_version_academic_year", "statutory_spec_version", ["academic_year"])
    op.create_index("ix_statutory_spec_version_status", "statutory_spec_version", ["status"])
    op.create_index(
        "uq_spec_version", "statutory_spec_version",
        ["pack_code", "academic_year", "version"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_spec_version", table_name="statutory_spec_version")
    op.drop_index("ix_statutory_spec_version_status", table_name="statutory_spec_version")
    op.drop_index("ix_statutory_spec_version_academic_year", table_name="statutory_spec_version")
    op.drop_index("ix_statutory_spec_version_pack_code", table_name="statutory_spec_version")
    op.drop_table("statutory_spec_version")

    op.drop_index("ix_statutory_advisory_status", table_name="statutory_advisory")
    op.drop_index("ix_statutory_advisory_academic_year", table_name="statutory_advisory")
    op.drop_index("ix_statutory_advisory_pack_code", table_name="statutory_advisory")
    op.drop_table("statutory_advisory")

    spec_version_status.drop(op.get_bind(), checkfirst=True)
    advisory_status.drop(op.get_bind(), checkfirst=True)
