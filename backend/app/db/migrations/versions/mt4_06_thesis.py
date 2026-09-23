"""MT-4 (thesis) — tenant scope + RLS for the thesis module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_06_thesis"
down_revision: Union[str, Sequence[str], None] = "mt4_05_funding"
branch_labels = None
depends_on = None

_TABLES = ('examination', 'examiner_nomination', 'thesis', 'thesis_correction')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
