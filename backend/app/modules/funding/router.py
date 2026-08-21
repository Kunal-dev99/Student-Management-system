"""Funding HTTP endpoints (arch §11.5 — funding)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.funding.repository import FundingRepository
from app.modules.funding.schemas import (
    ArrangementCreate,
    ArrangementOut,
    ChangeRequest,
    FundingSourceOut,
)
from app.modules.funding.service import FundingService
from app.modules.student_record.router import scoped_ids

student_router = APIRouter(prefix="/students", tags=["funding"])
funding_router = APIRouter(prefix="/funding", tags=["funding"])
sources_router = APIRouter(prefix="/funding-sources", tags=["funding"])


def _svc(session: AsyncSession) -> FundingService:
    return FundingService(FundingRepository(session))


@sources_router.get("", response_model=list[FundingSourceOut], summary="List funding sources")
async def list_sources(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("funding.read")),
) -> list[FundingSourceOut]:
    return [FundingSourceOut.model_validate(s) for s in await _svc(session).list_sources()]


@student_router.get("/{student_id}/funding", response_model=list[ArrangementOut], summary="Student funding (row-scoped)")
async def list_funding(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("funding.read")),
) -> list[ArrangementOut]:
    allowed = await scoped_ids(principal, session)
    rows = await _svc(session).list_arrangements(student_id, allowed_ids=allowed)
    return [ArrangementOut.model_validate(r) for r in rows]


@student_router.post("/{student_id}/funding", response_model=ArrangementOut, status_code=201, summary="Create funding arrangement")
async def create_funding(
    student_id: uuid.UUID,
    body: ArrangementCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("funding.change")),
) -> ArrangementOut:
    a = await _svc(session).create_arrangement(student_id, body)
    names = await FundingRepository(session).source_names()
    return ArrangementOut.model_validate(await _svc(session)._arrangement_dict(a, names))


@funding_router.post("/{arrangement_id}/change", response_model=ArrangementOut, summary="Change funding (close current, open new)")
async def change_funding(
    arrangement_id: uuid.UUID,
    body: ChangeRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("funding.change")),
) -> ArrangementOut:
    a = await _svc(session).change(arrangement_id, body)
    names = await FundingRepository(session).source_names()
    return ArrangementOut.model_validate(await _svc(session)._arrangement_dict(a, names))


@funding_router.post("/{arrangement_id}/end", response_model=ArrangementOut, summary="End a funding arrangement")
async def end_funding(
    arrangement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("funding.change")),
) -> ArrangementOut:
    a = await _svc(session).end(arrangement_id)
    names = await FundingRepository(session).source_names()
    return ArrangementOut.model_validate(await _svc(session)._arrangement_dict(a, names))
