"""MT-4 (intelligence) — tenant scope + RLS for the intelligence module.

Fan-out of the MT-2/MT-3 pattern (see app/db/tenant_ddl.py).
"""
from __future__ import annotations

from typing import Sequence, Union

from app.db.tenant_ddl import scope_tables, unscope_tables

revision: str = "mt4_23_intelligence"
down_revision: Union[str, Sequence[str], None] = "mt4_22_icr"
branch_labels = None
depends_on = None

_TABLES = ('driver_snapshot', 'evidence_claim', 'intelligence_telemetry', 'prediction_snapshot', 'engagement_event', 'engagement_snapshot', 'intervention_action', 'intervention_outcome', 'intervention_plan', 'supervision_commitment', 'change_finding', 'document_chunk', 'document_version', 'policy_proposal', 'policy_version')


def upgrade() -> None:
    scope_tables(_TABLES)


def downgrade() -> None:
    unscope_tables(_TABLES)
