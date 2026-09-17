"""Per-profile muted rule keys — lets an admin inhibit a specific cross-field / format rule for
one profile without touching the shared spec pack. Used to work around bad rules that arrived via
an accepted advisory: the offending pack still exists (so old returns can be re-produced byte for
byte), but the current profile can opt out.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "w3_profile_muted_rules"
# Two heads existed before this migration (a supervisor-profile branch and the ICR G5 advisory
# branch). Depend on both so alembic collapses them into a single lineage cleanly.
down_revision: Union[str, Sequence[str], None] = ("w2_supervisor_profile", "icr_g5_advisory_ingestion")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "report_profile",
        sa.Column("muted_rule_keys", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )


def downgrade() -> None:
    op.drop_column("report_profile", "muted_rule_keys")
