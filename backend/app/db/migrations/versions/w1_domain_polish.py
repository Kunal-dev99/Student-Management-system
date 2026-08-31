"""W1 — domain polish (opportunity_type, paused status, funding types, area hierarchy).

Additive only:
- W1.1 research_opportunity.opportunity_type (funded / partially_funded / unfunded); backfilled
       from stipend_amount at migration time.
- W1.3 opportunity_status enum extended with 'paused' (Postgres-only DDL; SQLite tests use
       string+CHECK via create_all in the fixture).
- W1.4 funding_type enum extended with 'scholarship', 'employer', 'mixed'.
- W1.5 research_area.parent_area_id self-FK for hierarchical areas.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "w1_domain_polish"
down_revision: Union[str, Sequence[str], None] = "icr_g25_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    pg = bind.dialect.name == "postgresql"

    # W1.3 — enum extend on Postgres. SQLite renders enums as VARCHAR+CHECK; create_all in tests
    # regenerates the whole check with the new value automatically.
    if pg:
        op.execute("ALTER TYPE opportunity_status ADD VALUE IF NOT EXISTS 'paused'")
        op.execute("ALTER TYPE funding_type ADD VALUE IF NOT EXISTS 'scholarship'")
        op.execute("ALTER TYPE funding_type ADD VALUE IF NOT EXISTS 'employer'")
        op.execute("ALTER TYPE funding_type ADD VALUE IF NOT EXISTS 'mixed'")

    # W1.1 — opportunity_type on research_opportunity.
    if pg:
        op.execute(
            "CREATE TYPE opportunity_funding AS ENUM "
            "('funded','partially_funded','unfunded')"
        )
    op.add_column(
        "research_opportunity",
        sa.Column(
            "opportunity_type",
            sa.Enum("funded", "partially_funded", "unfunded", name="opportunity_funding", create_type=False),
            nullable=False,
            server_default="funded",
        ),
    )
    op.create_index(
        "ix_research_opportunity_opportunity_type",
        "research_opportunity",
        ["opportunity_type"],
    )

    # W1.2 — backfill: stipend_amount > 0 → funded, else unfunded. 'partially_funded' is only ever
    # set by a human (an opportunity with a stipend but no fee waiver etc.), so we don't try to
    # infer it — 'funded' vs 'unfunded' is the safe partition.
    # Postgres needs explicit casts from text literal → enum type; SQLite is happy with strings.
    if pg:
        op.execute(
            "UPDATE research_opportunity "
            "SET opportunity_type = (CASE "
            "WHEN stipend_amount IS NOT NULL AND stipend_amount > 0 THEN 'funded' "
            "ELSE 'unfunded' END)::opportunity_funding"
        )
    else:
        op.execute(
            "UPDATE research_opportunity "
            "SET opportunity_type = CASE "
            "WHEN stipend_amount IS NOT NULL AND stipend_amount > 0 THEN 'funded' "
            "ELSE 'unfunded' END"
        )

    # W1.5 — research_area.parent_area_id
    op.add_column(
        "research_area",
        sa.Column("parent_area_id", sa.Uuid(), nullable=True),
    )
    with op.batch_alter_table("research_area") as batch:
        batch.create_foreign_key(
            "fk_research_area_parent_area_id_research_area",
            "research_area",
            ["parent_area_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_research_area_parent_area_id",
        "research_area",
        ["parent_area_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_area_parent_area_id", table_name="research_area")
    with op.batch_alter_table("research_area") as batch:
        batch.drop_constraint("fk_research_area_parent_area_id_research_area", type_="foreignkey")
    op.drop_column("research_area", "parent_area_id")

    op.drop_index("ix_research_opportunity_opportunity_type", table_name="research_opportunity")
    op.drop_column("research_opportunity", "opportunity_type")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS opportunity_funding")
    # Postgres does not support removing enum values, so 'paused' and the three funding_type
    # values stay in place after downgrade — they are inert if unused.
