"""Relationship-signal endpoint.

Scoped to the calling supervisor — the URL takes the student id, the supervisor id is
derived from the principal. Refuses if the supervisor doesn't currently supervise the
student. Never exposes anyone else's signal.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict as _asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_principal
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.relationship.service import signal_for_pair
from app.modules.supervision.repository import SupervisionRepository

router = APIRouter(prefix="/supervision", tags=["relationship-signal"])


@router.get(
    "/relationship-signal/{student_id}",
    summary="Relationship trajectory signal for a student in the caller's caseload",
)
async def get_signal(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    if principal.person_id is None:
        raise HTTPException(status_code=404, detail="No supervisor record linked to this account")

    # Guard: the student must be in the calling supervisor's active caseload.
    relationships = await SupervisionRepository(session).active_for_supervisor(principal.person_id)
    if not any(r.student_id == student_id for r in relationships):
        raise HTTPException(status_code=404, detail="Student not in your caseload")

    signal = await signal_for_pair(session, student_id, principal.person_id)
    return {
        "studentId": signal.student_id,
        "supervisorPersonId": signal.supervisor_person_id,
        "label": signal.label,
        "reasoning": signal.reasoning,
        "provenance": {
            "source": signal.provenance_source,
            "model": signal.provenance_model,
        },
        "evidenceTotals": signal.evidence_totals,
        # Return the evidence too so the UI can render "why" beside the label —
        # grounding-through-transparency.
        "evidence": [
            {
                "kind": e.kind,
                "at": e.at.isoformat(),
                "author": e.author,
                "text": e.text,
            }
            for e in signal.evidence
        ],
    }
