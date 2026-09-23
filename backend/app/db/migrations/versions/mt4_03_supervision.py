"""MT-4 (supervision) — tenant scope + RLS for the supervision module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_03_supervision"
down_revision: Union[str, Sequence[str], None] = "mt4_02_person"
branch_labels = None
depends_on = None

_TABLES = ('supervision_meeting', 'supervisor_relationship', 'supervisor_profile', 'supervisor_profile_area', 'supervisor_assignment_request')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
