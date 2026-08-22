"""Funding HTTP endpoints (arch §11.5 — funding)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.errors import NotFoundError
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.funding.repository import FundingRepository
from app.modules.funding.schemas import (
    ArrangementCreate,
    ArrangementOut,
    ChangeRequest,
    FundingSourceOut,
    MarkPaidRequest,
    PaymentOut,
    PaymentStatusRequest,
    ScheduleRequest,
    WaiverCreate,
    WaiverOut,
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


# --- Phase 4B.7 — stipend payment schedule ---

@funding_router.get("/{arrangement_id}/payments", response_model=list[PaymentOut], summary="Instalments for an arrangement")
async def list_payments(
    arrangement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("funding.read")),
) -> list[PaymentOut]:
    return [PaymentOut.model_validate(p) for p in await _svc(session).payments_for_arrangement(arrangement_id)]


@funding_router.post("/{arrangement_id}/payments/schedule", response_model=list[PaymentOut], status_code=201, summary="Generate the payment schedule")
async def generate_schedule(
    arrangement_id: uuid.UUID,
    body: ScheduleRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("funding.change")),
) -> list[PaymentOut]:
    rows = await _svc(session).generate_schedule(
        arrangement_id, frequency=body.frequency, instalments=body.instalments,
        first_due=body.first_due, annual_amount=body.annual_amount,
    )
    return [PaymentOut.model_validate(p) for p in rows]


@funding_router.post("/payments/{payment_id}/approve", response_model=PaymentOut, summary="Approve an instalment")
async def approve_payment(
    payment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("funding.change")),
) -> PaymentOut:
    return PaymentOut.model_validate(await _svc(session).approve_payment(payment_id))


@funding_router.post("/payments/{payment_id}/paid", response_model=PaymentOut, summary="Mark an instalment paid")
async def mark_paid(
    payment_id: uuid.UUID,
    body: MarkPaidRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("funding.change")),
) -> PaymentOut:
    return PaymentOut.model_validate(
        await _svc(session).mark_paid(payment_id, paid_on=body.paid_on, finance_reference=body.finance_reference)
    )


@funding_router.post("/payments/{payment_id}/status", response_model=PaymentOut, summary="Hold / cancel an instalment")
async def set_payment_status(
    payment_id: uuid.UUID,
    body: PaymentStatusRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("funding.change")),
) -> PaymentOut:
    return PaymentOut.model_validate(await _svc(session).set_payment_status(payment_id, body.status, body.note))


@student_router.get("/{student_id}/payments", response_model=list[PaymentOut], summary="All instalments for a student (row-scoped)")
async def student_payments(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("funding.read")),
) -> list[PaymentOut]:
    allowed = await scoped_ids(principal, session)
    rows = await _svc(session).payments_for_student(student_id, allowed_ids=allowed)
    return [PaymentOut.model_validate(p) for p in rows]


@student_router.get("/{student_id}/payment-summary", summary="Paid / committed / outstanding + overdue instalments")
async def payment_summary(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("funding.read")),
) -> dict:
    allowed = await scoped_ids(principal, session)
    await _svc(session).payments_for_student(student_id, allowed_ids=allowed)  # scope check
    return await _svc(session).payment_summary(student_id)


# --- Phase 4B.7 — fee waivers ---

@student_router.get("/{student_id}/fee-waivers", response_model=list[WaiverOut], summary="Fee waivers (row-scoped)")
async def list_waivers(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("funding.read")),
) -> list[WaiverOut]:
    allowed = await scoped_ids(principal, session)
    return [WaiverOut.model_validate(w) for w in await _svc(session).waivers_for_student(student_id, allowed_ids=allowed)]


@student_router.post("/{student_id}/fee-waivers", response_model=WaiverOut, status_code=201, summary="Record a fee waiver")
async def create_waiver(
    student_id: uuid.UUID,
    body: WaiverCreate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("funding.change")),
) -> WaiverOut:
    return WaiverOut.model_validate(await _svc(session).create_waiver(
        student_id, kind=body.kind, amount=body.amount, percentage=body.percentage,
        currency=body.currency, academic_year=body.academic_year,
        arrangement_id=body.arrangement_id, note=body.note,
    ))


# --- Phase 6.3 — funding lineage and integrity ---

@student_router.get("/{student_id}/funding-lineage",
                    summary="Student → project → award → funder → arrangement → stipend")
async def funding_lineage(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("funding.read")),
) -> dict:
    from app.modules.funding.lineage import FundingLineageService

    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        raise NotFoundError("Student not found")
    return await FundingLineageService(session).lineage(student_id)


@funding_router.post("/fee-waivers/{waiver_id}/approve", response_model=WaiverOut, summary="Approve a fee waiver")
async def approve_waiver(
    waiver_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("funding.change")),
) -> WaiverOut:
    return WaiverOut.model_validate(await _svc(session).approve_waiver(waiver_id, principal.user_id))
