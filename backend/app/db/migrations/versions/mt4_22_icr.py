"""MT-4 (icr) — tenant scope + RLS for the icr module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_22_icr"
down_revision: Union[str, Sequence[str], None] = "mt4_21_pattern_lab"
branch_labels = None
depends_on = None

_TABLES = ('icr_clinical_placement', 'icr_independent_tutor', 'icr_independent_tutor_note', 'icr_bench_fee_allocation', 'icr_bench_fee_drawdown', 'icr_partner_affiliation')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
