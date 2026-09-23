"""MT-4 (funding) — tenant scope + RLS for the funding module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_05_funding"
down_revision: Union[str, Sequence[str], None] = "mt4_04_progression"
branch_labels = None
depends_on = None

_TABLES = ('cost_centre', 'fee_waiver', 'funding_arrangement', 'funding_source', 'project_code', 'stipend_payment')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
