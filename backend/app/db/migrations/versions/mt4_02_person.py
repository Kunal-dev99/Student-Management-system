"""MT-4 (person) — tenant scope + RLS for the person module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_02_person"
down_revision: Union[str, Sequence[str], None] = "mt4_01_student_record"
branch_labels = None
depends_on = None

_TABLES = ('person_contact', 'person_merge_record', 'person_relationship')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
