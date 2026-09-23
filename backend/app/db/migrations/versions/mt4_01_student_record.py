"""MT-4 (01) — tenant scope + RLS for student_record's remaining tables.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py) to the rest of the
student_record module. person/programme/student/department were done in MT-2/MT-3.
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_01_student_record"
down_revision: Union[str, Sequence[str], None] = "mt3_tenant_rls"
branch_labels = None
depends_on = None

_TABLES = ("research_area", "research_project", "student_lifecycle_event")


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
