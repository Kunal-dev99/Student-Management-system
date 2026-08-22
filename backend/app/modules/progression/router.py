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
    AppealDecisionRequest,
    AppealOut,
    AppealRequest,
    DecideRequest,
    MilestoneDefinitionCreate,
    MilestoneDefinitionOut,
    MilestoneOut,
    PanelMemberOut,
    PanelMemberRequest,
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
    m, _next = await svc.decide(
        milestone_id, body.outcome, body.rationale, principal.user_id,
        conditions=body.conditions, outcome_letter=body.outcome_letter,
        require_panel=body.require_panel,
    )
    defn = await ProgressionRepository(session).get_definition(m.milestone_definition_id)
    return MilestoneOut.model_validate(svc._milestone_dict(m, defn))


# --- Phase 4B.6 — review panel, conditions sign-off, appeals ---

@milestone_router.get("/{milestone_id}/review", summary="Full review detail (panel, conditions, appeal window)")
async def review_detail(
    milestone_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("progression.read")),
) -> dict:
    return await _svc(session).review_detail(milestone_id)


@milestone_router.get("/{milestone_id}/panel", response_model=list[PanelMemberOut], summary="Review panel members")
async def list_panel(
    milestone_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("progression.read")),
) -> list[PanelMemberOut]:
    return [PanelMemberOut.model_validate(p) for p in await _svc(session).panel_for_milestone(milestone_id)]


@milestone_router.post("/{milestone_id}/panel", response_model=list[PanelMemberOut], status_code=201, summary="Add a panel member")
async def add_panel_member(
    milestone_id: uuid.UUID,
    body: PanelMemberRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("progression.decide")),
) -> list[PanelMemberOut]:
    rows = await _svc(session).add_panel_member(milestone_id, body.person_id, body.role, body.is_independent)
    return [PanelMemberOut.model_validate(p) for p in rows]


@milestone_router.post("/{milestone_id}/conditions/sign-off", summary="Sign off that conditions were met")
async def sign_off_conditions(
    milestone_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("progression.decide")),
) -> dict:
    return await _svc(session).sign_off_conditions(milestone_id)


@milestone_router.get("/{milestone_id}/appeals", response_model=list[AppealOut], summary="Appeals against this decision")
async def list_appeals(
    milestone_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("progression.read")),
) -> list[AppealOut]:
    return [AppealOut.model_validate(a) for a in await _svc(session).appeals_for_milestone(milestone_id)]


@milestone_router.post("/{milestone_id}/appeals", response_model=AppealOut, status_code=201, summary="Submit an appeal")
async def submit_appeal(
    milestone_id: uuid.UUID,
    body: AppealRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("progression.read")),
) -> AppealOut:
    # A student appeals their own decision, so this is guarded by progression.read.
    return AppealOut.model_validate(await _svc(session).submit_appeal(milestone_id, body.grounds))


@milestone_router.post("/appeals/{appeal_id}/decide", response_model=AppealOut, summary="Decide an appeal")
async def decide_appeal(
    appeal_id: uuid.UUID,
    body: AppealDecisionRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("progression.decide")),
) -> AppealOut:
    return AppealOut.model_validate(
        await _svc(session).decide_appeal(appeal_id, body.status, body.decision_note, principal.user_id)
    )
