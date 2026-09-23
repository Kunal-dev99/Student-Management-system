"""MT-4 (taught) — tenant scope + RLS for the taught module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_07_taught"
down_revision: Union[str, Sequence[str], None] = "mt4_06_thesis"
branch_labels = None
depends_on = None

_TABLES = ('assessment_result', 'dissertation', 'module_assessment', 'module_enrolment', 'module_offering', 'taught_award', 'taught_module')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
