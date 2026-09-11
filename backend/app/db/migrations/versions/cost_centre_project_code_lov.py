"""Cost centre + project code as first-class LOVs (Settings → List of values)."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "cost_centre_project_code_lov"
down_revision: Union[str, Sequence[str], None] = "value_set_overrides"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("cost_centre", "project_code"):
        op.create_table(
            table,
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True),
                      server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name=f"uq_{table}_code"),
        )


def downgrade() -> None:
    op.drop_table("project_code")
    op.drop_table("cost_centre")
