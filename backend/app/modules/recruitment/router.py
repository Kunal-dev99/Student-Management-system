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


async def _person_names(session: AsyncSession, person_ids) -> dict[str, str]:
    """Fetch given/family names for a batch of person ids so list rows can be enriched."""
    from sqlalchemy import select
    from app.modules.person.models import Person
    ids = list({p for p in person_ids if p})
    if not ids:
        return {}
    rows = (await session.execute(
        select(Person.id, Person.given_name, Person.family_name).where(Person.id.in_(ids))
    )).all()
    return {str(pid): f"{gn} {fn}" for pid, gn, fn in rows}

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
    search: str | None = Query(None, description="match applicant name"),
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.read")),
) -> dict:
    rows, total = await _svc(session).list_applications(
        limit=page.limit, offset=page.offset, stage=stage, search=search
    )
    names = await _person_names(session, [r.person_id for r in rows])
    data = []
    for r in rows:
        d = ApplicationOut.model_validate(r).model_dump(by_alias=True)
        d["personName"] = names.get(str(r.person_id))
        data.append(d)
    return list_envelope(data, limit=page.limit, total=total)


@app_router.post("", response_model=ApplicationOut, status_code=201, summary="Create application")
async def create_application(
    body: ApplicationCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> ApplicationOut:
    return ApplicationOut.model_validate(await _svc(session).create_application(body))


@app_router.get("/{aid}", summary="Get application")
async def get_application(
    aid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.read")),
) -> dict:
    row = await _svc(session).get_application(aid)
    names = await _person_names(session, [row.person_id])
    out = ApplicationOut.model_validate(row).model_dump(by_alias=True)
    out["personName"] = names.get(str(row.person_id))
    return out


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
