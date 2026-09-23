"""MT-4 (assistant) — tenant scope + RLS for the assistant module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_20_assistant"
down_revision: Union[str, Sequence[str], None] = "mt4_19_documents"
branch_labels = None
depends_on = None

_TABLES = ('assistant_unmatched_query', 'assistant_write_intent')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
