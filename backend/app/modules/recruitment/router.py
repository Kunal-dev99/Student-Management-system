"""Recruitment HTTP endpoints (arch §11.5 — recruitment)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_principal, require_permission
from app.core.pagination import PageParams, list_envelope, page_params
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.recruitment.repository import RecruitmentRepository
from app.modules.recruitment.schemas import (
    AdvanceRequest,
    ApplicationCreate,
    ApplicationOut,
    AssessRequest,
    OpportunityCreate,
    OpportunityOut,
    OpportunityUpdate,
    PipelineOut,
    TransitionRequest,
)
from app.modules.recruitment.service import RecruitmentService

opp_router = APIRouter(prefix="/opportunities", tags=["recruitment"])
app_router = APIRouter(prefix="/applications", tags=["recruitment"])
pipeline_router = APIRouter(prefix="/recruitment", tags=["recruitment"])


def _svc(session: AsyncSession) -> RecruitmentService:
    return RecruitmentService(RecruitmentRepository(session))


# --- Opportunities ---
@opp_router.get("", summary="List opportunities")
async def list_opportunities(
    page: PageParams = Depends(page_params),
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.read")),
) -> dict:
    rows, total = await _svc(session).list_opportunities(limit=page.limit, offset=page.offset, status=status)
    data = [OpportunityOut.model_validate(o).model_dump(by_alias=True) for o in rows]
    return list_envelope(data, limit=page.limit, total=total)


@opp_router.post("", response_model=OpportunityOut, status_code=201, summary="Create opportunity")
async def create_opportunity(
    body: OpportunityCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> OpportunityOut:
    return OpportunityOut.model_validate(await _svc(session).create_opportunity(body))


@opp_router.get("/{oid}", response_model=OpportunityOut, summary="Get opportunity")
async def get_opportunity(
    oid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.read")),
) -> OpportunityOut:
    return OpportunityOut.model_validate(await _svc(session).get_opportunity(oid))


@opp_router.patch("/{oid}", response_model=OpportunityOut, summary="Update opportunity")
async def update_opportunity(
    oid: uuid.UUID,
    body: OpportunityUpdate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> OpportunityOut:
    return OpportunityOut.model_validate(
        await _svc(session).update_opportunity(oid, body.model_dump(exclude_unset=True))
    )


@opp_router.post("/{oid}/transition", response_model=OpportunityOut, summary="Transition status")
async def transition_opportunity(
    oid: uuid.UUID,
    body: TransitionRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> OpportunityOut:
    return OpportunityOut.model_validate(await _svc(session).transition_opportunity(oid, body.to_status))


# --- Applications ---
@app_router.get("", summary="List applications")
async def list_applications(
    page: PageParams = Depends(page_params),
    stage: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.read")),
) -> dict:
    rows, total = await _svc(session).list_applications(limit=page.limit, offset=page.offset, stage=stage)
    data = [ApplicationOut.model_validate(a).model_dump(by_alias=True) for a in rows]
    return list_envelope(data, limit=page.limit, total=total)


@app_router.post("", response_model=ApplicationOut, status_code=201, summary="Create application")
async def create_application(
    body: ApplicationCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> ApplicationOut:
    return ApplicationOut.model_validate(await _svc(session).create_application(body))


@app_router.get("/{aid}", response_model=ApplicationOut, summary="Get application")
async def get_application(
    aid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.read")),
) -> ApplicationOut:
    return ApplicationOut.model_validate(await _svc(session).get_application(aid))


@app_router.post("/{aid}/advance", response_model=ApplicationOut, summary="Advance stage")
async def advance_application(
    aid: uuid.UUID,
    body: AdvanceRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("recruitment.write")),
) -> ApplicationOut:
    app = await _svc(session).advance(aid, body.to_stage, body.reason, principal.user_id)
    return ApplicationOut.model_validate(app)


@app_router.post("/{aid}/assess", response_model=ApplicationOut, summary="Record assessment")
async def assess_application(
    aid: uuid.UUID,
    body: AssessRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("recruitment.write")),
) -> ApplicationOut:
    app = await _svc(session).assess(
        aid, decision=body.decision, rationale=body.rationale,
        criteria=body.criteria, user_id=principal.user_id,
    )
    return ApplicationOut.model_validate(app)


# --- Pipeline ---
@pipeline_router.get("/pipeline", response_model=PipelineOut, summary="Counts by stage")
async def pipeline(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.read")),
) -> PipelineOut:
    counts, total = await _svc(session).pipeline()
    return PipelineOut(counts=counts, total=total)
