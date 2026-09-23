"""MT-4 (progression) — tenant scope + RLS for the progression module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_04_progression"
down_revision: Union[str, Sequence[str], None] = "mt4_03_supervision"
branch_labels = None
depends_on = None

_TABLES = ('milestone', 'milestone_definition', 'progression_appeal', 'progression_review', 'review_panel_member')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
