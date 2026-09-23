"""MT-4 (recruitment) — tenant scope + RLS for the recruitment module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_08_recruitment"
down_revision: Union[str, Sequence[str], None] = "mt4_07_taught"
branch_labels = None
depends_on = None

_TABLES = ('application', 'application_assessment', 'candidate_stage_history', 'research_opportunity', 'interview', 'interview_panellist', 'offer_condition', 'reference_request')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
