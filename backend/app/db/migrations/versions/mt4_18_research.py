"""MT-4 (research) — tenant scope + RLS for the research module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_18_research"
down_revision: Union[str, Sequence[str], None] = "mt4_17_portal"
branch_labels = None
depends_on = None

_TABLES = ('research_award', 'research_demand')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
