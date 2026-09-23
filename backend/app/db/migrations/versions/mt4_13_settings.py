"""MT-4 (settings) — tenant scope + RLS for the settings module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_13_settings"
down_revision: Union[str, Sequence[str], None] = "mt4_12_exports"
branch_labels = None
depends_on = None

_TABLES = ('institution_setting', 'value_set_override')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
