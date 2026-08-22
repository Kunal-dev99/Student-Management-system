"""Funding business rules (arch §8.9).

A funding change closes the current arrangement and opens a new one in one transaction, so a
student's funding history is preserved. (Finance notification via the outbox is Phase 2.)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.funding.constants import (
    COMMITTED_PAYMENT_STATES,
    INSTALMENTS_PER_YEAR,
    FundingStatus,
    FundingType,
    PaymentFrequency,
    PaymentStatus,
    WaiverKind,
)
from app.modules.funding.models import (
    FeeWaiver,
    FundingArrangement,
    StipendPayment,
)
from app.modules.funding.repository import FundingRepository
from app.modules.funding.schemas import ArrangementCreate, ChangeRequest
from app.modules.student_record.repository import StudentRepository


def _add_months(d: date, months: int) -> date:
    """Add whole months, clamping the day to the target month's length."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def _step_months(freq: PaymentFrequency) -> int:
    return {
        PaymentFrequency.monthly: 1,
        PaymentFrequency.quarterly: 3,
        PaymentFrequency.termly: 4,
        PaymentFrequency.annual: 12,
        PaymentFrequency.one_off: 0,
    }[freq]


class FundingService:
    def __init__(self, repo: FundingRepository) -> None:
        self.repo = repo
        self.session = repo.session

    async def list_sources(self):
        return await self.repo.list_sources()

    async def _arrangement_dict(self, a: FundingArrangement, names: dict) -> dict:
        return {
            "id": a.id,
            "studentId": a.student_id,
            "fundingType": a.funding_type,
            "fundingSourceId": a.funding_source_id,
            "fundingSourceName": names.get(a.funding_source_id) if a.funding_source_id else None,
            "stipendAmount": a.stipend_amount,
            "currency": a.currency,
            "validFrom": a.valid_from,
            "validTo": a.valid_to,
            "status": a.status,
            "createdAt": a.created_at,
            "costCentre": a.cost_centre,
            "projectCode": a.project_code,
            "funderReference": a.funder_reference,
            "contributionPct": a.contribution_pct,
            "researchAwardId": a.research_award_id,
            "paymentFrequency": a.payment_frequency,
        }

    async def list_arrangements(self, student_id: uuid.UUID, *, allowed_ids=None) -> list[dict]:
        student = await StudentRepository(self.session).get(student_id, allowed_ids=allowed_ids)
        if student is None:
            raise NotFoundError("Student not found")
        rows = await self.repo.arrangements_for_student(student_id)
        names = await self.repo.source_names()
        return [await self._arrangement_dict(a, names) for a in rows]

    async def create_arrangement(self, student_id: uuid.UUID, data: ArrangementCreate) -> FundingArrangement:
        if await StudentRepository(self.session).get(student_id) is None:
            raise NotFoundError("Student not found")
        arrangement = FundingArrangement(
            student_id=student_id,
            funding_type=data.funding_type,
            funding_source_id=data.funding_source_id,
            stipend_amount=data.stipend_amount,
            currency=data.currency,
            valid_from=data.valid_from or date.today(),
            valid_to=None,
            status=FundingStatus.active,
            cost_centre=data.cost_centre,
            project_code=data.project_code,
            funder_reference=data.funder_reference,
            contribution_pct=data.contribution_pct,
            research_award_id=data.research_award_id,
        )
        self.repo.add(arrangement)
        await self.session.commit()
        await self.session.refresh(arrangement)
        return arrangement

    async def _get(self, arrangement_id: uuid.UUID) -> FundingArrangement:
        a = await self.repo.get(arrangement_id)
        if a is None:
            raise NotFoundError("Funding arrangement not found")
        return a

    async def change(self, arrangement_id: uuid.UUID, data: ChangeRequest) -> FundingArrangement:
        current = await self._get(arrangement_id)
        if current.valid_to is not None:
            raise WorkflowError("This arrangement has already ended; nothing to change")
        # Close current, open new — one transaction (arch §8.9).
        current.valid_to = date.today()
        current.status = FundingStatus.changed
        new = FundingArrangement(
            student_id=current.student_id,
            funding_type=data.funding_type,
            funding_source_id=data.funding_source_id,
            stipend_amount=data.stipend_amount,
            currency=data.currency,
            valid_from=date.today(),
            valid_to=None,
            status=FundingStatus.active,
            cost_centre=data.cost_centre,
            project_code=data.project_code,
            funder_reference=data.funder_reference,
            contribution_pct=data.contribution_pct,
            research_award_id=data.research_award_id,
        )
        self.repo.add(new)
        await self.session.flush()  # populate new.id before referencing it in the event

        # Notify Finance of the funding change via the outbox (arch §8.9, §10.2).
        from app.modules.workflow.engine import WorkflowEngine
        WorkflowEngine(self.session).emit(
            "funding_arrangement", new.id, "funding.changed",
            {"studentId": str(new.student_id), "fundingType": new.funding_type.value},
        )

        await self.session.commit()
        await self.session.refresh(new)
        return new

    async def end_active_for_student(self, student_id: uuid.UUID) -> int:
        """End every active arrangement for a student. Flushes only — caller owns the
        transaction (used by graduation, arch §8.11). Returns how many were ended."""
        count = 0
        for a in await self.repo.arrangements_for_student(student_id):
            if a.valid_to is None:
                a.valid_to = date.today()
                a.status = FundingStatus.ended
                count += 1
        await self.session.flush()
        return count

    async def end(self, arrangement_id: uuid.UUID) -> FundingArrangement:
        a = await self._get(arrangement_id)
        if a.valid_to is None:
            a.valid_to = date.today()
            a.status = FundingStatus.ended
            # Cancel any instalments not yet paid — funding has stopped (arch §8.9).
            for p in await self.repo.payments_for_arrangement(a.id):
                if p.status in (PaymentStatus.scheduled, PaymentStatus.approved):
                    p.status = PaymentStatus.cancelled
                    p.note = (p.note or "") + " [auto-cancelled: arrangement ended]"
            await self.session.commit()
            await self.session.refresh(a)
        return a

    # --- Phase 4B.7 — stipend payment schedule ---

    def _payment_out(self, p: StipendPayment) -> dict:
        return {
            "id": str(p.id), "arrangementId": str(p.arrangement_id), "studentId": str(p.student_id),
            "sequence": p.sequence, "dueDate": p.due_date.isoformat(),
            "amount": str(p.amount), "currency": p.currency,
            "status": p.status.value if hasattr(p.status, "value") else p.status,
            "paidOn": p.paid_on.isoformat() if p.paid_on else None,
            "financeReference": p.finance_reference, "note": p.note,
        }

    async def payments_for_arrangement(self, arrangement_id: uuid.UUID) -> list[dict]:
        return [self._payment_out(p) for p in await self.repo.payments_for_arrangement(arrangement_id)]

    async def payments_for_student(self, student_id: uuid.UUID, *, allowed_ids=None) -> list[dict]:
        student = await StudentRepository(self.session).get(student_id, allowed_ids=allowed_ids)
        if student is None:
            raise NotFoundError("Student not found")
        return [self._payment_out(p) for p in await self.repo.payments_for_student(student_id)]

    async def generate_schedule(
        self, arrangement_id: uuid.UUID, *, frequency: PaymentFrequency,
        instalments: int | None = None, first_due: date | None = None,
        annual_amount: Decimal | None = None,
    ) -> list[dict]:
        """Build the instalment schedule for an arrangement (arch §8.9).

        The stipend is an annual figure; instalments divide it by the frequency. Regenerating is
        refused once any instalment has been paid, so finance history is never rewritten.
        """
        a = await self._get(arrangement_id)
        existing = await self.repo.payments_for_arrangement(arrangement_id)
        if any(p.status == PaymentStatus.paid for p in existing):
            raise ConflictError("This arrangement already has paid instalments; cancel them first")
        # Replace any previous (unpaid) schedule.
        for p in existing:
            await self.session.delete(p)

        annual = annual_amount if annual_amount is not None else a.stipend_amount
        if annual is None:
            raise WorkflowError("This arrangement has no stipend amount to schedule")
        count = instalments or INSTALMENTS_PER_YEAR[frequency]
        if count <= 0:
            raise WorkflowError("instalments must be greater than zero")

        per_year = INSTALMENTS_PER_YEAR[frequency]
        per_instalment = (Decimal(annual) / Decimal(per_year)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        start = first_due or a.valid_from or date.today()
        step = _step_months(frequency)

        rows = []
        for i in range(count):
            due = start if step == 0 else _add_months(start, step * i)
            payment = StipendPayment(
                arrangement_id=a.id, student_id=a.student_id, sequence=i + 1,
                due_date=due, amount=per_instalment, currency=a.currency,
                status=PaymentStatus.scheduled,
            )
            self.repo.add(payment)
            rows.append(payment)
        a.payment_frequency = frequency
        await self.session.commit()
        return [self._payment_out(p) for p in rows]

    async def _get_payment(self, payment_id: uuid.UUID) -> StipendPayment:
        p = await self.repo.get_payment(payment_id)
        if p is None:
            raise NotFoundError("Stipend payment not found")
        return p

    async def approve_payment(self, payment_id: uuid.UUID) -> dict:
        p = await self._get_payment(payment_id)
        if p.status != PaymentStatus.scheduled:
            raise WorkflowError(f"Only a scheduled payment can be approved (this one is {p.status.value})")
        p.status = PaymentStatus.approved
        await self.session.commit()
        return self._payment_out(p)

    async def mark_paid(self, payment_id: uuid.UUID, *, paid_on: date | None, finance_reference: str | None) -> dict:
        p = await self._get_payment(payment_id)
        if p.status == PaymentStatus.paid:
            raise ConflictError("This payment is already marked paid")
        if p.status == PaymentStatus.cancelled:
            raise WorkflowError("A cancelled payment cannot be paid")
        p.status = PaymentStatus.paid
        p.paid_on = paid_on or date.today()
        p.finance_reference = finance_reference
        await self.session.flush()

        # Tell Finance the instalment landed (outbox → finance adapter, arch §10.2).
        from app.modules.workflow.engine import WorkflowEngine

        WorkflowEngine(self.session).emit(
            "stipend_payment", p.id, "funding.changed",
            {"studentId": str(p.student_id), "event": "stipend_paid",
             "amount": str(p.amount), "currency": p.currency, "financeReference": finance_reference},
        )
        await self.session.commit()
        return self._payment_out(p)

    async def set_payment_status(self, payment_id: uuid.UUID, status: PaymentStatus, note: str | None) -> dict:
        p = await self._get_payment(payment_id)
        if p.status == PaymentStatus.paid and status != PaymentStatus.paid:
            raise WorkflowError("A paid instalment cannot be reverted")
        p.status = status
        if note:
            p.note = note
        await self.session.commit()
        return self._payment_out(p)

    async def payment_summary(self, student_id: uuid.UUID) -> dict:
        rows = await self.repo.payments_for_student(student_id)
        paid = sum((p.amount for p in rows if p.status == PaymentStatus.paid), Decimal("0"))
        committed = sum((p.amount for p in rows if p.status in COMMITTED_PAYMENT_STATES), Decimal("0"))
        outstanding = committed - paid
        overdue = [
            self._payment_out(p) for p in rows
            if p.status in (PaymentStatus.scheduled, PaymentStatus.approved) and p.due_date < date.today()
        ]
        return {
            "studentId": str(student_id),
            "instalments": len(rows),
            "paidTotal": str(paid),
            "committedTotal": str(committed),
            "outstandingTotal": str(outstanding),
            "currency": rows[0].currency if rows else None,
            "overdue": overdue,
        }

    # --- Phase 4B.7 — fee waivers ---

    def _waiver_out(self, w: FeeWaiver) -> dict:
        return {
            "id": str(w.id), "studentId": str(w.student_id),
            "arrangementId": str(w.arrangement_id) if w.arrangement_id else None,
            "kind": w.kind.value if hasattr(w.kind, "value") else w.kind,
            "amount": str(w.amount) if w.amount is not None else None,
            "percentage": w.percentage, "currency": w.currency,
            "academicYear": w.academic_year,
            "approved": w.approved_at is not None,
            "note": w.note,
        }

    async def waivers_for_student(self, student_id: uuid.UUID, *, allowed_ids=None) -> list[dict]:
        student = await StudentRepository(self.session).get(student_id, allowed_ids=allowed_ids)
        if student is None:
            raise NotFoundError("Student not found")
        return [self._waiver_out(w) for w in await self.repo.waivers_for_student(student_id)]

    async def create_waiver(
        self, student_id: uuid.UUID, *, kind: WaiverKind, amount: Decimal | None,
        percentage: int | None, currency: str | None, academic_year: str | None,
        arrangement_id: uuid.UUID | None, note: str | None,
    ) -> dict:
        if await StudentRepository(self.session).get(student_id) is None:
            raise NotFoundError("Student not found")
        if amount is None and percentage is None:
            raise WorkflowError("A waiver needs either an amount or a percentage")
        if percentage is not None and not (0 < percentage <= 100):
            raise WorkflowError("percentage must be between 1 and 100")
        w = FeeWaiver(
            student_id=student_id, arrangement_id=arrangement_id, kind=kind, amount=amount,
            percentage=percentage, currency=currency, academic_year=academic_year, note=note,
        )
        self.repo.add(w)
        await self.session.commit()
        await self.session.refresh(w)
        return self._waiver_out(w)

    async def approve_waiver(self, waiver_id: uuid.UUID, user_id) -> dict:
        w = (await self.session.get(FeeWaiver, waiver_id))
        if w is None:
            raise NotFoundError("Fee waiver not found")
        if w.approved_at is not None:
            raise ConflictError("This waiver is already approved")
        w.approved_at = datetime.now(timezone.utc)
        w.approved_by_user_id = user_id
        await self.session.commit()
        return self._waiver_out(w)
