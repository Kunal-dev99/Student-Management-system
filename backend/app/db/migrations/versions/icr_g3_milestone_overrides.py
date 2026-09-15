"""ICR G3 - per-student milestone overrides + ad-hoc milestones.

Additive / widening only:
- milestone.origin (template [default] / override / ad_hoc) — drives regeneration precedence.
- milestone.name (nullable) — the title of an ad-hoc milestone (template ones use the definition).
- milestone.milestone_definition_id relaxed to NULLABLE so an ad-hoc milestone needs no definition.

Every existing milestone becomes origin='template' with its definition intact, so current
behaviour is unchanged.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "icr_g3_milestone_overrides"
down_revision: Union[str, Sequence[str], None] = "icr_g1_taught_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


milestone_origin = sa.Enum("template", "override", "ad_hoc", name="milestone_origin")


def upgrade() -> None:
    bind = op.get_bind()
    milestone_origin.create(bind, checkfirst=True)

    op.add_column(
        "milestone",
        sa.Column(
            "origin",
            sa.Enum("template", "override", "ad_hoc", name="milestone_origin", create_type=False),
            nullable=False,
            server_default="template",
        ),
    )
    op.add_column("milestone", sa.Column("name", sa.String(length=200), nullable=True))
    op.alter_column("milestone", "milestone_definition_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    op.alter_column("milestone", "milestone_definition_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("milestone", "name")
    op.drop_column("milestone", "origin")
    milestone_origin.drop(op.get_bind(), checkfirst=True)
