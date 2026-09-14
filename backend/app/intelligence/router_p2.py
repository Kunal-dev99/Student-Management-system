"""AI-P2 endpoints — interventions, commitments, engagement trajectory."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_read_session, get_session
from app.intelligence.engagement import EngagementService
from app.intelligence.interventions import ActionExecutor, InterventionPlanner
from app.intelligence.models_p2 import (
    InterventionAction,
    InterventionPlan,
    SupervisionCommitment,
)
from app.intelligence.schemas_p2 import (
    EngagementSnapshotOut,
    EngagementTrajectoryOut,
    InterventionActionOut,
    InterventionPlanCreate,
    InterventionPlanOut,
    SupervisionCommitmentOut,
)
from app.intelligence.supervision_ai import CommitmentExtractor

router_p2 = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _plan_out(plan: InterventionPlan, actions: list[InterventionAction]) -> InterventionPlanOut:
    return InterventionPlanOut(
        id=plan.id, case_ref=plan.case_ref, student_id=plan.student_id,
        rationale=plan.rationale, source_signal=plan.source_signal,
        reassess_at=plan.reassess_at, status=plan.status,
        confirmed_at=plan.confirmed_at,
        actions=[InterventionActionOut.model_validate(a) for a in actions],
    )


# ---- Interventions -----------------------------------------------------------

@router_p2.post("/interventions/plan", response_model=InterventionPlanOut, status_code=201,
                 summary="Stage a draft intervention plan (idempotent by signal + actions)")
async def stage_plan(
    body: InterventionPlanCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.write")),
) -> InterventionPlanOut:
    plan = await InterventionPlanner(session, principal).stage(body)
    actions = (await session.execute(
        select(InterventionAction).where(InterventionAction.plan_id == plan.id)
    )).scalars().all()
    await session.commit()
    return _plan_out(plan, list(actions))


@router_p2.post("/interventions/{plan_id}/confirm", response_model=InterventionPlanOut,
                 summary="Confirm a staged plan — every action executes through a domain service")
async def confirm_plan(
    plan_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.write")),
) -> InterventionPlanOut:
    plan = await ActionExecutor(session, principal).confirm(plan_id)
    actions = (await session.execute(
        select(InterventionAction).where(InterventionAction.plan_id == plan_id)
    )).scalars().all()
    await session.commit()
    return _plan_out(plan, list(actions))


@router_p2.post("/interventions/{plan_id}/cancel", response_model=InterventionPlanOut,
                 summary="Cancel a draft or confirmed plan")
async def cancel_plan(
    plan_id: uuid.UUID,
    reason: str | None = None,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.write")),
) -> InterventionPlanOut:
    plan = await InterventionPlanner(session, principal).cancel(plan_id, reason=reason)
    actions = (await session.execute(
        select(InterventionAction).where(InterventionAction.plan_id == plan_id)
    )).scalars().all()
    await session.commit()
    return _plan_out(plan, list(actions))


@router_p2.get("/students/{student_id}/interventions", response_model=list[InterventionPlanOut],
                summary="Every intervention plan staged for one student, newest first")
async def list_plans_for_student(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _: Principal = Depends(require_permission("student.read")),
) -> list[InterventionPlanOut]:
    plans = (await session.execute(
        select(InterventionPlan)
        .where(InterventionPlan.student_id == student_id)
        .order_by(InterventionPlan.created_at.desc())
    )).scalars().all()
    if not plans:
        return []
    plan_ids = [p.id for p in plans]
    actions = (await session.execute(
        select(InterventionAction).where(InterventionAction.plan_id.in_(plan_ids))
    )).scalars().all()
    by_plan: dict[uuid.UUID, list[InterventionAction]] = {}
    for a in actions:
        by_plan.setdefault(a.plan_id, []).append(a)
    return [_plan_out(p, by_plan.get(p.id, [])) for p in plans]


@router_p2.get("/interventions/{plan_id}", response_model=InterventionPlanOut,
                summary="Read one plan and its actions")
async def get_plan(
    plan_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _: Principal = Depends(require_permission("student.read")),
) -> InterventionPlanOut:
    plan = await session.get(InterventionPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    actions = (await session.execute(
        select(InterventionAction).where(InterventionAction.plan_id == plan_id)
    )).scalars().all()
    return _plan_out(plan, list(actions))


class ProposeSignalIn(BaseModel):
    signal_kind: str
    signal_detail: str
    case_ref: str
    student_id: uuid.UUID | None = None


@router_p2.post("/interventions/propose-from-signal",
                 summary="LLM-assisted action-type suggestion for a signal (never persists)")
async def propose_from_signal(
    body: ProposeSignalIn,
    session: AsyncSession = Depends(get_read_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> dict[str, Any]:
    return await InterventionPlanner(session, principal).propose_from_signal(
        signal_kind=body.signal_kind, signal_detail=body.signal_detail,
        case_ref=body.case_ref, student_id=body.student_id,
    )


# ---- Supervision commitments -------------------------------------------------

class CommitmentProposalIn(BaseModel):
    student_id: uuid.UUID
    notes: str


class CommitmentPersistIn(BaseModel):
    student_id: uuid.UUID
    confirmed: list[dict[str, Any]]


@router_p2.post("/supervision/meetings/{meeting_id}/commitments/propose",
                 summary="Deterministic proposal of commitments from meeting notes")
async def propose_commitments(
    meeting_id: uuid.UUID,
    body: CommitmentProposalIn,
    session: AsyncSession = Depends(get_read_session),
    _: Principal = Depends(require_permission("student.read")),
) -> list[dict[str, Any]]:
    return await CommitmentExtractor(session).propose(meeting_id, body.student_id, body.notes)


@router_p2.post("/supervision/meetings/{meeting_id}/commitments",
                 response_model=list[SupervisionCommitmentOut], status_code=201,
                 summary="Persist reviewer-confirmed commitments for a meeting")
async def persist_commitments(
    meeting_id: uuid.UUID,
    body: CommitmentPersistIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.write")),
) -> list[SupervisionCommitmentOut]:
    rows = await CommitmentExtractor(session).persist_confirmed(
        meeting_id, body.student_id, body.confirmed,
        confirmed_by_user_id=principal.user_id,
    )
    await session.commit()
    return [SupervisionCommitmentOut.model_validate(r) for r in rows]


@router_p2.get("/supervision/meetings/{meeting_id}/commitments",
                response_model=list[SupervisionCommitmentOut],
                summary="Every commitment persisted against one meeting")
async def list_commitments(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _: Principal = Depends(require_permission("student.read")),
) -> list[SupervisionCommitmentOut]:
    rows = (await session.execute(
        select(SupervisionCommitment)
        .where(SupervisionCommitment.meeting_id == meeting_id)
        .order_by(SupervisionCommitment.created_at.asc())
    )).scalars().all()
    return [SupervisionCommitmentOut.model_validate(r) for r in rows]


# ---- Engagement trajectory ---------------------------------------------------

@router_p2.post("/engagement/{student_id}/compute", response_model=EngagementSnapshotOut,
                 summary="Compute and persist a rolling-window engagement snapshot")
async def compute_engagement(
    student_id: uuid.UUID,
    window_days: int = 90,
    engine: str = "rules",
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_permission("student.read")),
) -> EngagementSnapshotOut:
    snap = await EngagementService(session).compute_snapshot(
        student_id, window_days=window_days, engine=engine,
    )
    await session.commit()
    return EngagementSnapshotOut.model_validate(snap)


@router_p2.get("/engagement/{student_id}", response_model=EngagementTrajectoryOut,
                summary="Trajectory chart data — snapshots + recent events")
async def engagement_trajectory(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _: Principal = Depends(require_permission("student.read")),
) -> EngagementTrajectoryOut:
    snapshots, events = await EngagementService(session).trajectory(student_id)
    return EngagementTrajectoryOut(
        student_id=student_id,
        points=[EngagementSnapshotOut.model_validate(s) for s in snapshots],
        recent_events=[
            {"kind": e.kind, "weight": e.weight,
             "occurred_at": e.occurred_at.isoformat(),
             "reason_code": e.reason_code}
            for e in events
        ],
    )
