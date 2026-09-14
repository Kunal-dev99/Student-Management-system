"""Intelligence router — additive, not disruptive.

Every endpoint here is guarded by the same principal + row scoping the domain
services already enforce. Nothing on this router mutates domain tables; execution
of any drafted intervention still goes through the existing domain endpoints after
the user confirms.

Phase 1 endpoints:
    GET  /intelligence/students/{id}                 — CaseContext for one student
    GET  /intelligence/evidence/{artefact_id}        — EvidenceClaims for an artefact
    GET  /intelligence/predictions/{student_id}/history — RiskStoryline series
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import Evidence
from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_read_session, get_session
from app.intelligence.ai_bridge import intelligence_narrate
from app.intelligence.context import CaseContextBuilder
from app.intelligence.evidence import EvidenceService
from app.intelligence.models import DriverSnapshot, PredictionSnapshot
from app.intelligence.schemas import (
    CaseContext,
    DriverSnapshotOut,
    EvidenceClaimOut,
    PredictionSnapshotOut,
    RiskStorylineOut,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/students/{student_id}", response_model=CaseContext,
             summary="CaseContext for one student (Phase 1 foundations)")
async def student_context(
    student_id: uuid.UUID,
    record_evidence: bool = Query(default=False,
        description="Persist EvidenceClaims for this call. Off by default — reads are free."),
    enable_llm: bool = Query(default=False,
        description="Attach a one-paragraph LLM-narrated summary. Off by default."),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> CaseContext:
    """Assemble the student's CaseContext through domain services only.

    Row scoping is enforced by the domain reads inside the builder — a student the
    caller cannot see returns 404, never a partial context.
    """
    artefact_id = uuid.uuid4() if record_evidence else None
    evidence = EvidenceService(session) if record_evidence else None
    builder = CaseContextBuilder(session, principal, evidence=evidence)
    ctx = await builder.for_student(student_id, artefact_id=artefact_id)
    if record_evidence:
        await session.commit()
        # Carry the artefact id back on the context for the caller to fetch evidence.
        ctx.pending_action_plan_id = artefact_id

    if enable_llm:
        # narrate()'s anti-hallucination check only allows the model to quote numbers
        # that appear verbatim in `evidence.figures` (never `context`) — so every
        # atomic fact we want the model ALLOWED to mention has to be a figure, not
        # just contextual framing. Getting this wrong has two failure modes, both
        # seen while building this: put nothing here and quiet domains read as
        # "empty" (highlights-only bug); put facts only in `context` and the model's
        # accurate quote of a real number gets rejected as "ungrounded" and the whole
        # call falls back needlessly. One figure per domain, built from real facts,
        # avoids both.
        figures: dict[str, str] = {
            "domain_count": str(len(ctx.domain_summaries)),
            "missing_source_count": str(len(ctx.missing_sources)),
        }
        for ds in ctx.domain_summaries[:5]:
            if ds.highlights:
                detail = "; ".join(ds.highlights[:2])
            elif ds.facts:
                detail = "; ".join(f"{f.get('label')}={f.get('value')}" for f in ds.facts[:4])
            elif ds.counts:
                detail = "; ".join(f"{k}={v}" for k, v in ds.counts.items())
            else:
                detail = "no data recorded"
            figures[f"domain_{ds.domain}"] = detail
        evidence = Evidence(
            figures=figures,
            context={"missing": [m.source for m in ctx.missing_sources]},
        )
        fallback = ("Case has {domain_count} domain summaries and "
                    "{missing_source_count} missing source(s).")
        narration = await intelligence_narrate(
            feature="case_copilot",
            evidence=evidence,
            question="Summarise this student's case in one short paragraph.",
            fallback_template=fallback,
            principal_id=principal.user_id,
        )
        ctx.narrated_summary = {
            "body": narration.body,
            "source": narration.provenance.source,
            "model": narration.provenance.model,
        }

    return ctx


@router.get("/evidence/{artefact_id}", response_model=list[EvidenceClaimOut],
             summary="Every evidence claim recorded against one AI artefact")
async def evidence_for_artefact(
    artefact_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _: Principal = Depends(require_permission("student.read")),
) -> list[EvidenceClaimOut]:
    claims = await EvidenceService(session).for_artefact(artefact_id)
    return [EvidenceClaimOut.model_validate(c) for c in claims]


@router.get("/predictions/{student_id}/history", response_model=RiskStorylineOut,
             summary="Prediction history + drivers for one student (Risk Storyline)")
async def prediction_history(
    student_id: uuid.UUID,
    target: str = Query(..., description="Pattern Lab target key, e.g. funding_continuity"),
    session: AsyncSession = Depends(get_read_session),
    _: Principal = Depends(require_permission("ml.read")),
) -> RiskStorylineOut:
    """Every persisted prediction for (student, target), oldest first, with drivers grouped.

    A future request should also carry `ModelVersionBoundary` markers so the frontend
    knows where model changes make scores non-comparable — Phase 3 adds those.
    """
    points = (await session.execute(
        select(PredictionSnapshot)
        .where(PredictionSnapshot.student_id == student_id,
               PredictionSnapshot.target == target)
        .order_by(PredictionSnapshot.predicted_at.asc())
    )).scalars().all()

    if not points:
        raise HTTPException(status_code=404, detail="No predictions on record for this target")

    ids = [p.id for p in points]
    drivers = (await session.execute(
        select(DriverSnapshot).where(DriverSnapshot.prediction_id.in_(ids))
    )).scalars().all()

    grouped: dict[uuid.UUID, list[DriverSnapshotOut]] = {}
    for d in drivers:
        grouped.setdefault(d.prediction_id, []).append(DriverSnapshotOut.model_validate(d))

    return RiskStorylineOut(
        student_id=student_id,
        target=target,
        points=[PredictionSnapshotOut.model_validate(p) for p in points],
        drivers_by_prediction=grouped,
    )
