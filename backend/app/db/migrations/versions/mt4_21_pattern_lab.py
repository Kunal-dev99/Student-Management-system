"""MT-4 (pattern_lab) — tenant scope + RLS for the pattern_lab module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_21_pattern_lab"
down_revision: Union[str, Sequence[str], None] = "mt4_20_assistant"
branch_labels = None
depends_on = None

_TABLES = ('ml_dataset', 'ml_finding', 'ml_model', 'ml_model_version', 'ml_prediction', 'ml_training_run')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
