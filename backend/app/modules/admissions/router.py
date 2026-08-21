"""Admissions HTTP endpoints (arch §11.5 — admissions)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.admissions.repository import AdmissionsRepository
from app.modules.admissions.schemas import AcceptRequest, OfferCreate, OfferOut
from app.modules.admissions.service import AdmissionsService
from app.modules.student_record.schemas import StudentOut

# Offer creation hangs off an application; the rest act on the offer resource.
app_scoped = APIRouter(prefix="/applications", tags=["admissions"])
offer_router = APIRouter(prefix="/offers", tags=["admissions"])


def _svc(session: AsyncSession) -> AdmissionsService:
    return AdmissionsService(AdmissionsRepository(session))


@app_scoped.get("/{application_id}/offer", response_model=OfferOut | None, summary="Get offer for application")
async def get_offer_for_application(
    application_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.read")),
):
    offer = await _svc(session).offer_for_application(application_id)
    return OfferOut.model_validate(offer) if offer else None


@app_scoped.post("/{application_id}/offer", response_model=OfferOut, status_code=201, summary="Create offer")
async def create_offer(
    application_id: uuid.UUID,
    body: OfferCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> OfferOut:
    return OfferOut.model_validate(await _svc(session).create_offer(application_id, body.conditions))


@offer_router.post("/{offer_id}/issue", response_model=OfferOut, summary="Issue offer")
async def issue_offer(
    offer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> OfferOut:
    return OfferOut.model_validate(await _svc(session).issue_offer(offer_id))


@offer_router.post("/{offer_id}/decline", response_model=OfferOut, summary="Decline offer")
async def decline_offer(
    offer_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> OfferOut:
    return OfferOut.model_validate(await _svc(session).decline_offer(offer_id))


@offer_router.post(
    "/{offer_id}/accept",
    response_model=StudentOut,
    status_code=201,
    summary="Accept offer — creates a student reusing the same person_id",
)
async def accept_offer(
    offer_id: uuid.UUID,
    body: AcceptRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.write")),
) -> StudentOut:
    student = await _svc(session).accept_offer(
        offer_id,
        programme_id=body.programme_id,
        study_mode=body.study_mode,
        start_date=body.start_date,
        user_id=principal.user_id,
    )
    return StudentOut.model_validate(student)
