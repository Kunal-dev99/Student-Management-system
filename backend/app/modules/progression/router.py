"""Progression HTTP endpoints (arch §11.5 — progression)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.progression.repository import ProgressionRepository
from app.modules.progression.schemas import (
    DecideRequest,
    MilestoneDefinitionCreate,
    MilestoneDefinitionOut,
    MilestoneOut,
    SubmitRequest,
)
from app.modules.progression.service import ProgressionService
from app.modules.student_record.router import scoped_ids

programme_router = APIRouter(prefix="/programmes", tags=["progression"])
student_router = APIRouter(prefix="/students", tags=["progression"])
milestone_router = APIRouter(prefix="/milestones", tags=["progression"])


def _svc(session: AsyncSession) -> ProgressionService:
    return ProgressionService(ProgressionRepository(session))


# --- Definitions (configurable per programme) ---
@programme_router.get("/{programme_id}/milestone-definitions", response_model=list[MilestoneDefinitionOut], summary="List milestone definitions")
async def list_definitions(
    programme_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("progression.read")),
) -> list[MilestoneDefinitionOut]:
    rows = await _svc(session).list_definitions(programme_id)
    return [MilestoneDefinitionOut.model_validate(d) for d in rows]


@programme_router.post("/{programme_id}/milestone-definitions", response_model=MilestoneDefinitionOut, status_code=201, summary="Add milestone definition")
async def create_definition(
    programme_id: uuid.UUID,
    body: MilestoneDefinitionCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> MilestoneDefinitionOut:
    return MilestoneDefinitionOut.model_validate(await _svc(session).create_definition(programme_id, body))


# --- Milestones (per student, row-scoped) ---
@student_router.get("/{student_id}/milestones", response_model=list[MilestoneOut], summary="Student milestones")
async def list_milestones(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("progression.read")),
) -> list[MilestoneOut]:
    allowed = await scoped_ids(principal, session)
    rows = await _svc(session).list_milestones(student_id, allowed_ids=allowed)
    return [MilestoneOut.model_validate(r) for r in rows]


@milestone_router.post("/{milestone_id}/submit", response_model=MilestoneOut, summary="Submit a milestone")
async def submit_milestone(
    milestone_id: uuid.UUID,
    body: SubmitRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("progression.read")),
) -> MilestoneOut:
    svc = _svc(session)
    m = await svc.submit(milestone_id, body.student_submission_ref)
    defn = await ProgressionRepository(session).get_definition(m.milestone_definition_id)
    return MilestoneOut.model_validate(svc._milestone_dict(m, defn))


@milestone_router.post("/{milestone_id}/decide", response_model=MilestoneOut, summary="Panel decision")
async def decide_milestone(
    milestone_id: uuid.UUID,
    body: DecideRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("progression.decide")),
) -> MilestoneOut:
    svc = _svc(session)
    m, _next = await svc.decide(milestone_id, body.outcome, body.rationale, principal.user_id)
    defn = await ProgressionRepository(session).get_definition(m.milestone_definition_id)
    return MilestoneOut.model_validate(svc._milestone_dict(m, defn))
