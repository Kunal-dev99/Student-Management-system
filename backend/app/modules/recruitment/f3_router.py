"""F3 — HTTP routes for references, interviews, offer conditions, fee-status/visa.

Kept in a companion router so the base recruitment router stays readable. Aggregated in
``app/api/v1/routes.py`` alongside the other module routers.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.errors import NotFoundError
from app.db.session import get_session
from app.modules.recruitment.f3_models import (
    InterviewOutcome, InterviewStatus,
    OfferConditionStatus, ReferenceRequestStatus,
)
from app.modules.recruitment.f3_service import (
    InterviewService, OfferConditionService, ReferenceService,
)
from app.modules.recruitment.models import Application


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class ReferenceCreate(_Camel):
    referee_name: str
    referee_email: str
    referee_affiliation: str | None = None


class ReferenceOut(_Camel):
    id: uuid.UUID
    referee_name: str
    referee_email: str
    referee_affiliation: str | None
    status: ReferenceRequestStatus
    requested_at: datetime
    submitted_at: datetime | None
    response_text: str | None


class ReferenceSubmitBody(_Camel):
    response_text: str
    response_document_ref: str | None = None


class InterviewCreate(_Camel):
    scheduled_at: datetime
    location: str | None = None


class InterviewOut(_Camel):
    id: uuid.UUID
    scheduled_at: datetime
    location: str | None
    status: InterviewStatus
    outcome: InterviewOutcome
    notes: str | None


class PanellistCreate(_Camel):
    person_id: uuid.UUID
    role: str | None = None


class OutcomeBody(_Camel):
    outcome: InterviewOutcome
    notes: str | None = None


class ConditionCreate(_Camel):
    description: str
    satisfy_by: date | None = None


class ConditionOut(_Camel):
    id: uuid.UUID
    description: str
    satisfy_by: date | None
    status: OfferConditionStatus
    satisfied_at: datetime | None
    evidence_document_ref: str | None


class VisaCheckBody(_Camel):
    fee_status: str | None = None
    visa_required: bool | None = None
    complete_visa_check: bool | None = None


app_router = APIRouter(prefix="/applications", tags=["recruitment"])
conditions_router = APIRouter(prefix="/offers", tags=["admissions"])
public_ref_router = APIRouter(prefix="/public/references", tags=["recruitment"])


# ---- references (authenticated)

@app_router.get("/{aid}/references", response_model=list[ReferenceOut],
                summary="Reference requests on this application")
async def list_references(
    aid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.read")),
) -> list[ReferenceOut]:
    return [ReferenceOut.model_validate(r) for r in await ReferenceService(session).list_for(aid)]


@app_router.post("/{aid}/references", status_code=201,
                 summary="Request a reference (returns the one-time token URL)")
async def request_reference(
    aid: uuid.UUID,
    body: ReferenceCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> dict:
    row, token = await ReferenceService(session).request(
        aid, referee_name=body.referee_name, referee_email=body.referee_email,
        referee_affiliation=body.referee_affiliation,
    )
    return {
        "reference": ReferenceOut.model_validate(row).model_dump(by_alias=True),
        "submitToken": token,
        "submitUrl": f"/public/references/{token}",
    }


# ---- reference submission (unauthenticated, token-scoped)

@public_ref_router.post("/{token}", response_model=ReferenceOut,
                        summary="Referee submits a reference via their token")
async def submit_reference(
    token: str,
    body: ReferenceSubmitBody,
    session: AsyncSession = Depends(get_session),
) -> ReferenceOut:
    row = await ReferenceService(session).submit(
        token, text_body=body.response_text, document_ref=body.response_document_ref,
    )
    return ReferenceOut.model_validate(row)


# ---- interviews

@app_router.get("/{aid}/interviews", response_model=list[InterviewOut],
                summary="Interviews on this application")
async def list_interviews(
    aid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.read")),
) -> list[InterviewOut]:
    return [InterviewOut.model_validate(r) for r in await InterviewService(session).list_for(aid)]


@app_router.post("/{aid}/interviews", response_model=InterviewOut, status_code=201,
                 summary="Schedule an interview")
async def schedule_interview(
    aid: uuid.UUID,
    body: InterviewCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> InterviewOut:
    row = await InterviewService(session).schedule(
        aid, scheduled_at=body.scheduled_at, location=body.location,
    )
    return InterviewOut.model_validate(row)


@app_router.post("/interviews/{iid}/panellists", status_code=201,
                 summary="Add a panellist to an interview")
async def add_panellist(
    iid: uuid.UUID,
    body: PanellistCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> dict:
    p = await InterviewService(session).add_panellist(iid, person_id=body.person_id, role=body.role)
    return {"id": str(p.id), "interviewId": str(p.interview_id),
            "personId": str(p.person_id), "role": p.role}


@app_router.post("/interviews/{iid}/outcome", response_model=InterviewOut,
                 summary="Record the interview outcome (moves it to completed)")
async def interview_outcome(
    iid: uuid.UUID,
    body: OutcomeBody,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> InterviewOut:
    row = await InterviewService(session).record_outcome(
        iid, outcome=body.outcome, notes=body.notes,
    )
    return InterviewOut.model_validate(row)


# ---- offer conditions

@conditions_router.get("/{oid}/conditions", response_model=list[ConditionOut],
                       summary="First-class conditions on this offer")
async def list_conditions(
    oid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.read")),
) -> list[ConditionOut]:
    return [ConditionOut.model_validate(c) for c in await OfferConditionService(session).list_for(oid)]


@conditions_router.post("/{oid}/conditions", response_model=ConditionOut, status_code=201,
                        summary="Add a condition to an offer")
async def add_condition(
    oid: uuid.UUID,
    body: ConditionCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> ConditionOut:
    row = await OfferConditionService(session).add(
        oid, description=body.description, satisfy_by=body.satisfy_by,
    )
    return ConditionOut.model_validate(row)


@conditions_router.post("/{oid}/conditions/{cid}/satisfy", response_model=ConditionOut,
                        summary="Mark a condition satisfied")
async def satisfy_condition(
    oid: uuid.UUID, cid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> ConditionOut:
    return ConditionOut.model_validate(await OfferConditionService(session).satisfy(cid))


@conditions_router.post("/{oid}/conditions/{cid}/waive", response_model=ConditionOut,
                        summary="Waive a condition")
async def waive_condition(
    oid: uuid.UUID, cid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> ConditionOut:
    return ConditionOut.model_validate(await OfferConditionService(session).waive(cid))


# ---- fee status + visa

@app_router.patch("/{aid}/visa-check",
                  summary="Update fee status / visa flag / stamp the visa check as complete")
async def visa_check(
    aid: uuid.UUID,
    body: VisaCheckBody,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("recruitment.write")),
) -> dict:
    app_row = (await session.execute(
        select(Application).where(Application.id == aid)
    )).scalar_one_or_none()
    if app_row is None:
        raise NotFoundError("Application not found")
    if body.fee_status is not None:
        app_row.fee_status = body.fee_status
    if body.visa_required is not None:
        app_row.visa_required = body.visa_required
    if body.complete_visa_check is True and app_row.visa_check_completed_at is None:
        app_row.visa_check_completed_at = datetime.now(timezone.utc)
    if body.complete_visa_check is False:
        app_row.visa_check_completed_at = None
    await session.commit()
    return {
        "applicationId": str(aid),
        "feeStatus": app_row.fee_status,
        "visaRequired": app_row.visa_required,
        "visaCheckCompletedAt": app_row.visa_check_completed_at.isoformat()
                                if app_row.visa_check_completed_at else None,
    }
