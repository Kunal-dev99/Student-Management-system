"""MT-4 (exports) — tenant scope + RLS for the exports module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_12_exports"
down_revision: Union[str, Sequence[str], None] = "mt4_11_workflow"
branch_labels = None
depends_on = None

_TABLES = ('export_job', 'report_field_mapping', 'report_profile')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
