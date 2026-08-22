"""Research context endpoints (Phase 6.1 — awards, demand, position lineage)."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_read_session, get_session
from app.modules.research.constants import DemandStatus
from app.modules.research.repository import ResearchRepository
from app.modules.research.service import ResearchService

awards_router = APIRouter(prefix="/research-awards", tags=["research"])
demand_router = APIRouter(prefix="/research-demands", tags=["research"])
lineage_router = APIRouter(prefix="/opportunities", tags=["research"])


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class AwardCreate(_Camel):
    award_ref: str
    title: str
    funder_id: uuid.UUID | None = None
    principal_investigator_id: uuid.UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    value: Decimal | None = None
    currency: str | None = None


class AwardUpdate(_Camel):
    title: str | None = None
    funder_id: uuid.UUID | None = None
    end_date: date | None = None
    value: Decimal | None = None


class DemandCreate(_Camel):
    title: str
    research_award_id: uuid.UUID | None = None
    research_area_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    requested_places: int = 1
    justification: str | None = None
    target_start_date: date | None = None


class DemandTransition(_Camel):
    to_status: DemandStatus


def _svc(session: AsyncSession) -> ResearchService:
    return ResearchService(ResearchRepository(session))


# --- awards ---

@awards_router.get("", summary="Research awards (references; mastered in the Research system)")
async def list_awards(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("recruitment.read")),
) -> list[dict]:
    return await _svc(session).list_awards()


@awards_router.post("", status_code=201, summary="Record an award reference (manual fallback)")
async def create_award(
    body: AwardCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    svc = _svc(session)
    award = await svc.create_award(
        award_ref=body.award_ref, title=body.title, funder_id=body.funder_id,
        principal_investigator_id=body.principal_investigator_id,
        start_date=body.start_date, end_date=body.end_date,
        value=body.value, currency=body.currency,
    )
    return svc.award_out(award)


@awards_router.patch("/{award_id}", summary="Update a locally-held award")
async def update_award(
    award_id: uuid.UUID,
    body: AwardUpdate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    svc = _svc(session)
    award = await svc.update_award(award_id, body.model_dump(exclude_unset=True))
    return svc.award_out(award)


# --- demand ---

@demand_router.get("", summary="Research demand (the need for a researcher)")
async def list_demands(
    status: str | None = None,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("recruitment.read")),
) -> list[dict]:
    return await _svc(session).list_demands(status)


@demand_router.post("", status_code=201, summary="Raise a research demand")
async def create_demand(
    body: DemandCreate,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("recruitment.write")),
) -> dict:
    svc = _svc(session)
    demand = await svc.create_demand(
        title=body.title, research_award_id=body.research_award_id,
        research_area_id=body.research_area_id, department_id=body.department_id,
        requested_places=body.requested_places, justification=body.justification,
        target_start_date=body.target_start_date, raised_by_user_id=principal.user_id,
    )
    return svc.demand_out(demand)


@demand_router.post("/{demand_id}/transition", summary="Move demand through its lifecycle")
async def transition_demand(
    demand_id: uuid.UUID,
    body: DemandTransition,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> dict:
    svc = _svc(session)
    return svc.demand_out(await svc.transition_demand(demand_id, body.to_status))


# --- lineage ---

# --- Phase 7 (R5) — supervisor matching and the relationship graph ---

matching_router = APIRouter(prefix="/research", tags=["research"])
areas_router = APIRouter(prefix="/research-areas", tags=["research"])


@areas_router.get("", summary="Research areas (reference data)")
async def list_research_areas(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("student.read")),
) -> list[dict]:
    """Reference lookup. Needed because `/research/supervisor-suggestions` takes a
    `researchAreaId` and there was previously no way for a caller to discover one."""
    from sqlalchemy import select

    from app.modules.student_record.models import ResearchArea

    rows = (await session.execute(
        select(ResearchArea).order_by(ResearchArea.name)
    )).scalars().all()
    return [{"id": str(a.id), "name": a.name, "code": a.code} for a in rows]


class SuggestRequest(_Camel):
    research_area_id: uuid.UUID | None = None
    proposal_text: str | None = None
    limit: int = 10


@matching_router.post("/supervisor-suggestions", summary="Suggest supervisors, with explained scores")
async def suggest_supervisors(
    body: SuggestRequest,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("student.read")),
) -> dict:
    from app.modules.research.matching import MatchingService

    return await MatchingService(session).suggest_supervisors(
        research_area_id=body.research_area_id, proposal_text=body.proposal_text, limit=body.limit
    )


@matching_router.get("/graph", summary="Person ↔ research ↔ supervisor ↔ award ↔ funding")
async def relationship_graph(
    studentId: uuid.UUID | None = None,
    awardId: uuid.UUID | None = None,
    limit: int = 40,
    session: AsyncSession = Depends(get_read_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> dict:
    from app.modules.research.matching import MatchingService
    from app.modules.student_record.router import scoped_ids

    allowed = await scoped_ids(principal, session)
    return await MatchingService(session).relationship_graph(
        student_id=studentId, award_id=awardId, allowed_ids=allowed, limit=limit
    )


@lineage_router.get("/{opportunity_id}/lineage", summary="Award → demand → position → students")
async def position_lineage(
    opportunity_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("recruitment.read")),
) -> dict:
    return await _svc(session).position_lineage(opportunity_id)
