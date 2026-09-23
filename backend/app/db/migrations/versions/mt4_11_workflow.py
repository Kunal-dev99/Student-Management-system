"""MT-4 (workflow) — tenant scope + RLS for the workflow module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_11_workflow"
down_revision: Union[str, Sequence[str], None] = "mt4_10_completion"
branch_labels = None
depends_on = None

_TABLES = ('notification', 'outbox_event', 'task', 'workflow_definition', 'workflow_instance')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
