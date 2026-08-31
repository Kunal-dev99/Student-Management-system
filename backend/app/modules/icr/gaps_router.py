"""Endpoints for ICR gaps 2-5. Aggregated under /api/v1/icr next to the read views."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_read_session, get_session
from app.modules.icr.gaps_service import (
    BenchFeeService, ClinicalPlacementService, IndependentTutorService,
    PartnerAffiliationService, VALID_AFFILIATION_KINDS,
)


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# --------------------------- Gap 2 — Clinical placement -------------------

class PlacementIn(_Camel):
    trust_name: str
    specialty: str
    grade: str
    valid_from: date
    supervisor_name: str | None = None
    sessions_per_week: int | None = None
    notes: str | None = None


class PlacementOut(_Camel):
    id: uuid.UUID
    student_id: uuid.UUID
    trust_name: str
    specialty: str
    grade: str
    supervisor_name: str | None
    valid_from: date
    valid_to: date | None
    sessions_per_week: int | None
    notes: str | None


class EndBody(_Camel):
    valid_to: date


router = APIRouter(prefix="/icr", tags=["icr"])


@router.get("/students/{student_id}/placements", response_model=list[PlacementOut],
            summary="Gap 2 — SpR rotation posts held alongside the studentship")
async def list_placements(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("student.read")),
) -> list[PlacementOut]:
    return [PlacementOut.model_validate(r) for r in
            await ClinicalPlacementService(session).list_for(student_id)]


@router.post("/students/{student_id}/placements", response_model=PlacementOut, status_code=201,
             summary="Gap 2 — open a new clinical placement")
async def open_placement(
    student_id: uuid.UUID,
    body: PlacementIn,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> PlacementOut:
    row = await ClinicalPlacementService(session).open(
        student_id, trust_name=body.trust_name, specialty=body.specialty,
        grade=body.grade, valid_from=body.valid_from,
        supervisor_name=body.supervisor_name, sessions_per_week=body.sessions_per_week,
        notes=body.notes,
    )
    return PlacementOut.model_validate(row)


@router.post("/placements/{placement_id}/end", response_model=PlacementOut,
             summary="Gap 2 — end a current placement")
async def end_placement(
    placement_id: uuid.UUID,
    body: EndBody,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> PlacementOut:
    row = await ClinicalPlacementService(session).end(placement_id, valid_to=body.valid_to)
    return PlacementOut.model_validate(row)


# --------------------------- Gap 3 — Independent tutor + notes ------------

class TutorAssignIn(_Camel):
    tutor_person_id: uuid.UUID
    tutor_department_id: uuid.UUID | None = None


class TutorOut(_Camel):
    id: uuid.UUID
    student_id: uuid.UUID
    tutor_person_id: uuid.UUID
    tutor_department_id: uuid.UUID | None
    assigned_at: datetime
    ended_at: datetime | None


class TutorNoteIn(_Camel):
    body: str


class TutorNoteOut(_Camel):
    id: uuid.UUID
    tutor_id: uuid.UUID
    body: str
    authored_by_user_id: uuid.UUID | None
    authored_at: datetime


@router.get("/students/{student_id}/independent-tutor", summary="Gap 3 — current independent tutor")
async def get_current_tutor(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("student.read")),
) -> dict:
    row = await IndependentTutorService(session).current_for(student_id)
    if row is None:
        return {"currentTutor": None}
    return {"currentTutor": TutorOut.model_validate(row).model_dump(by_alias=True)}


@router.post("/students/{student_id}/independent-tutor", response_model=TutorOut, status_code=201,
             summary="Gap 3 — assign an independent tutor (outside-the-lab rule enforced)")
async def assign_tutor(
    student_id: uuid.UUID,
    body: TutorAssignIn,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> TutorOut:
    row = await IndependentTutorService(session).assign(
        student_id, tutor_person_id=body.tutor_person_id,
        tutor_department_id=body.tutor_department_id,
    )
    return TutorOut.model_validate(row)


@router.post("/independent-tutor/{tutor_id}/end", response_model=TutorOut,
             summary="Gap 3 — end an independent-tutor relationship")
async def end_tutor(
    tutor_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> TutorOut:
    row = await IndependentTutorService(session).end(tutor_id)
    return TutorOut.model_validate(row)


@router.get("/independent-tutor/{tutor_id}/notes", response_model=list[TutorNoteOut],
            summary="Gap 3 — private tutor-notes channel")
async def list_tutor_notes(
    tutor_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("student.read")),
) -> list[TutorNoteOut]:
    return [TutorNoteOut.model_validate(n) for n in
            await IndependentTutorService(session).notes(tutor_id)]


@router.post("/independent-tutor/{tutor_id}/notes", response_model=TutorNoteOut, status_code=201,
             summary="Gap 3 — add a private note")
async def add_tutor_note(
    tutor_id: uuid.UUID,
    body: TutorNoteIn,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("student.write")),
) -> TutorNoteOut:
    row = await IndependentTutorService(session).add_note(
        tutor_id, body=body.body, authored_by_user_id=principal.user_id,
    )
    return TutorNoteOut.model_validate(row)


# --------------------------- Gap 4 — Bench fees ----------------------------

class AllocationIn(_Camel):
    total_amount: Decimal
    currency: str = "GBP"
    valid_from: date
    valid_to: date | None = None
    funding_source_id: uuid.UUID | None = None
    cost_centre: str | None = None
    notes: str | None = None


class DrawdownIn(_Camel):
    amount: Decimal
    category: str
    description: str
    drawn_at: date
    invoice_ref: str | None = None


class DrawdownOut(_Camel):
    id: uuid.UUID
    allocation_id: uuid.UUID
    amount: Decimal
    category: str
    description: str
    drawn_at: date
    invoice_ref: str | None


@router.get("/students/{student_id}/bench-fees", summary="Gap 4 — bench-fee allocations + balances")
async def bench_fees(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("funding.read")),
) -> dict:
    return {"allocations": await BenchFeeService(session).allocations_for(student_id)}


@router.post("/students/{student_id}/bench-fees", status_code=201,
             summary="Gap 4 — allocate a new bench-fee budget")
async def allocate_bench_fee(
    student_id: uuid.UUID,
    body: AllocationIn,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("funding.change")),
) -> dict:
    a = await BenchFeeService(session).allocate(
        student_id, total_amount=body.total_amount, currency=body.currency,
        valid_from=body.valid_from, valid_to=body.valid_to,
        funding_source_id=body.funding_source_id,
        cost_centre=body.cost_centre, notes=body.notes,
    )
    return {"id": str(a.id), "totalAmount": str(a.total_amount),
            "currency": a.currency, "validFrom": a.valid_from.isoformat()}


@router.get("/bench-fees/{allocation_id}/drawdowns", response_model=list[DrawdownOut],
            summary="Gap 4 — draw-downs against an allocation")
async def list_drawdowns(
    allocation_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("funding.read")),
) -> list[DrawdownOut]:
    return [DrawdownOut.model_validate(r) for r in
            await BenchFeeService(session).drawdowns_for(allocation_id)]


@router.post("/bench-fees/{allocation_id}/drawdowns", response_model=DrawdownOut, status_code=201,
             summary="Gap 4 — record a draw-down (refused if it would exceed the allocation)")
async def add_drawdown(
    allocation_id: uuid.UUID,
    body: DrawdownIn,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("funding.change")),
) -> DrawdownOut:
    row = await BenchFeeService(session).drawdown(
        allocation_id, amount=body.amount, category=body.category,
        description=body.description, drawn_at=body.drawn_at, invoice_ref=body.invoice_ref,
    )
    return DrawdownOut.model_validate(row)


# --------------------------- Gap 5 — Partner affiliation -------------------

class AffiliationIn(_Camel):
    partner_name: str
    affiliation_kind: str
    valid_from: date
    valid_to: date | None = None
    partner_ref: str | None = None
    compliance: dict | None = None


class AffiliationOut(_Camel):
    id: uuid.UUID
    student_id: uuid.UUID
    partner_name: str
    affiliation_kind: str
    partner_ref: str | None
    valid_from: date
    valid_to: date | None
    compliance: dict | None
    active: bool


@router.get("/students/{student_id}/partner-affiliations",
            summary="Gap 5 — partner affiliations + compliance flags")
async def list_affiliations(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("student.read")),
) -> dict:
    rows = await PartnerAffiliationService(session).list_for(student_id)
    return {
        "affiliations": [
            {**AffiliationOut.model_validate(r).model_dump(by_alias=True),
             "complianceFlags": PartnerAffiliationService.compliance_expiry_flags(r)}
            for r in rows
        ],
        "allowedKinds": sorted(VALID_AFFILIATION_KINDS),
    }


@router.post("/students/{student_id}/partner-affiliations", response_model=AffiliationOut,
             status_code=201, summary="Gap 5 — record a partner affiliation")
async def add_affiliation(
    student_id: uuid.UUID,
    body: AffiliationIn,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> AffiliationOut:
    row = await PartnerAffiliationService(session).add(
        student_id, partner_name=body.partner_name, affiliation_kind=body.affiliation_kind,
        valid_from=body.valid_from, valid_to=body.valid_to,
        partner_ref=body.partner_ref, compliance=body.compliance,
    )
    return AffiliationOut.model_validate(row)


@router.post("/partner-affiliations/{affiliation_id}/end", response_model=AffiliationOut,
             summary="Gap 5 — end an affiliation")
async def end_affiliation(
    affiliation_id: uuid.UUID,
    body: EndBody,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> AffiliationOut:
    row = await PartnerAffiliationService(session).end(affiliation_id, valid_to=body.valid_to)
    return AffiliationOut.model_validate(row)
