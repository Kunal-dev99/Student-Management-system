"""Services for ICR gaps 2-5.

Each service owns a small aggregate: clinical placement, independent tutor + notes, bench-fee
allocation + draw-downs, partner affiliation. Read/write CRUD with the small handful of business
rules named in the model docstrings enforced here.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.icr.models import (
    BenchFeeAllocation, BenchFeeDrawdown, ClinicalPlacement,
    IndependentTutor, IndependentTutorNote, PartnerAffiliation,
)
from app.modules.person.models import Person
from app.modules.student_record.models import Student


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ Gap 2

class ClinicalPlacementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for(self, student_id: uuid.UUID) -> list[ClinicalPlacement]:
        return list((await self.session.execute(
            select(ClinicalPlacement)
            .where(ClinicalPlacement.student_id == student_id)
            .order_by(ClinicalPlacement.valid_from.desc())
        )).scalars().all())

    async def open(self, student_id: uuid.UUID, *, trust_name: str, specialty: str,
                   grade: str, valid_from: date, supervisor_name: str | None = None,
                   sessions_per_week: int | None = None, notes: str | None = None) -> ClinicalPlacement:
        row = ClinicalPlacement(
            student_id=student_id, trust_name=trust_name, specialty=specialty, grade=grade,
            supervisor_name=supervisor_name, valid_from=valid_from,
            sessions_per_week=sessions_per_week, notes=notes,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def end(self, placement_id: uuid.UUID, *, valid_to: date) -> ClinicalPlacement:
        row = (await self.session.execute(
            select(ClinicalPlacement).where(ClinicalPlacement.id == placement_id)
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Clinical placement not found")
        if row.valid_to is not None:
            raise ConflictError("Placement already ended")
        row.valid_to = valid_to
        await self.session.commit()
        await self.session.refresh(row)
        return row


# ------------------------------------------------------------------ Gap 3

class IndependentTutorService:
    """Outside-the-lab tutor with a hard department-independence gate."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def current_for(self, student_id: uuid.UUID) -> IndependentTutor | None:
        return (await self.session.execute(
            select(IndependentTutor)
            .where(IndependentTutor.student_id == student_id,
                   IndependentTutor.ended_at.is_(None))
            .order_by(IndependentTutor.assigned_at.desc())
        )).scalars().first()

    async def assign(self, student_id: uuid.UUID, *, tutor_person_id: uuid.UUID,
                     tutor_department_id: uuid.UUID | None) -> IndependentTutor:
        """Refused if the tutor shares the student's department (outside-the-lab rule)."""
        student = (await self.session.execute(
            select(Student).where(Student.id == student_id)
        )).scalar_one_or_none()
        if student is None:
            raise NotFoundError("Student not found")
        tutor = (await self.session.execute(
            select(Person).where(Person.id == tutor_person_id)
        )).scalar_one_or_none()
        if tutor is None:
            raise NotFoundError("Tutor person not found")
        if (student.department_id is not None
                and tutor_department_id is not None
                and student.department_id == tutor_department_id):
            raise WorkflowError(
                "Independent-tutor rule violated: tutor must be from a different department "
                "than the student's lab."
            )
        # Close any current tutor first — one active tutor at a time.
        current = await self.current_for(student_id)
        if current is not None:
            current.ended_at = _now()
        row = IndependentTutor(
            student_id=student_id, tutor_person_id=tutor_person_id,
            tutor_department_id=tutor_department_id, assigned_at=_now(),
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def end(self, tutor_id: uuid.UUID) -> IndependentTutor:
        row = (await self.session.execute(
            select(IndependentTutor).where(IndependentTutor.id == tutor_id)
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Independent tutor not found")
        if row.ended_at is not None:
            raise ConflictError("Already ended")
        row.ended_at = _now()
        await self.session.commit()
        await self.session.refresh(row)
        return row

    # notes
    async def add_note(self, tutor_id: uuid.UUID, *, body: str,
                       authored_by_user_id: uuid.UUID | None) -> IndependentTutorNote:
        tutor = (await self.session.execute(
            select(IndependentTutor).where(IndependentTutor.id == tutor_id)
        )).scalar_one_or_none()
        if tutor is None:
            raise NotFoundError("Independent tutor not found")
        note = IndependentTutorNote(
            tutor_id=tutor_id, body=body,
            authored_by_user_id=authored_by_user_id, authored_at=_now(),
        )
        self.session.add(note)
        await self.session.commit()
        await self.session.refresh(note)
        return note

    async def notes(self, tutor_id: uuid.UUID) -> list[IndependentTutorNote]:
        return list((await self.session.execute(
            select(IndependentTutorNote)
            .where(IndependentTutorNote.tutor_id == tutor_id)
            .order_by(IndependentTutorNote.authored_at.desc())
        )).scalars().all())


# ------------------------------------------------------------------ Gap 4

class BenchFeeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def allocations_for(self, student_id: uuid.UUID) -> list[dict]:
        rows = list((await self.session.execute(
            select(BenchFeeAllocation)
            .where(BenchFeeAllocation.student_id == student_id)
            .order_by(BenchFeeAllocation.valid_from.desc())
        )).scalars().all())
        out = []
        for a in rows:
            drawn = (await self.session.execute(
                select(func.coalesce(func.sum(BenchFeeDrawdown.amount), 0))
                .where(BenchFeeDrawdown.allocation_id == a.id)
            )).scalar() or Decimal(0)
            out.append({
                "id": str(a.id),
                "totalAmount": str(a.total_amount),
                "currency": a.currency,
                "validFrom": a.valid_from.isoformat(),
                "validTo": a.valid_to.isoformat() if a.valid_to else None,
                "costCentre": a.cost_centre,
                "notes": a.notes,
                "drawnAmount": str(drawn),
                "remainingAmount": str(a.total_amount - drawn),
            })
        return out

    async def allocate(self, student_id: uuid.UUID, *, total_amount: Decimal,
                       currency: str = "GBP", valid_from: date, valid_to: date | None = None,
                       funding_source_id: uuid.UUID | None = None,
                       cost_centre: str | None = None, notes: str | None = None) -> BenchFeeAllocation:
        if total_amount <= 0:
            raise WorkflowError("Bench-fee allocation must be > 0")
        row = BenchFeeAllocation(
            student_id=student_id, total_amount=total_amount, currency=currency,
            valid_from=valid_from, valid_to=valid_to,
            funding_source_id=funding_source_id, cost_centre=cost_centre, notes=notes,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def drawdown(self, allocation_id: uuid.UUID, *, amount: Decimal, category: str,
                       description: str, drawn_at: date, invoice_ref: str | None = None) -> BenchFeeDrawdown:
        alloc = (await self.session.execute(
            select(BenchFeeAllocation).where(BenchFeeAllocation.id == allocation_id)
        )).scalar_one_or_none()
        if alloc is None:
            raise NotFoundError("Bench-fee allocation not found")
        if amount <= 0:
            raise WorkflowError("Draw-down amount must be > 0")
        # Refuse overdraw against the allocation total.
        drawn = (await self.session.execute(
            select(func.coalesce(func.sum(BenchFeeDrawdown.amount), 0))
            .where(BenchFeeDrawdown.allocation_id == allocation_id)
        )).scalar() or Decimal(0)
        if drawn + amount > alloc.total_amount:
            raise WorkflowError(
                f"Draw-down of {amount} would exceed the allocation "
                f"({drawn}/{alloc.total_amount} drawn). Increase the allocation first."
            )
        row = BenchFeeDrawdown(
            allocation_id=allocation_id, amount=amount, category=category,
            description=description, drawn_at=drawn_at, invoice_ref=invoice_ref,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def drawdowns_for(self, allocation_id: uuid.UUID) -> list[BenchFeeDrawdown]:
        return list((await self.session.execute(
            select(BenchFeeDrawdown)
            .where(BenchFeeDrawdown.allocation_id == allocation_id)
            .order_by(BenchFeeDrawdown.drawn_at.desc())
        )).scalars().all())


# ------------------------------------------------------------------ Gap 5

VALID_AFFILIATION_KINDS = {"honorary_contract", "co_registration", "clinical_placement", "other"}


class PartnerAffiliationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for(self, student_id: uuid.UUID) -> list[PartnerAffiliation]:
        return list((await self.session.execute(
            select(PartnerAffiliation)
            .where(PartnerAffiliation.student_id == student_id)
            .order_by(PartnerAffiliation.valid_from.desc())
        )).scalars().all())

    async def add(self, student_id: uuid.UUID, *, partner_name: str, affiliation_kind: str,
                  valid_from: date, valid_to: date | None = None,
                  partner_ref: str | None = None,
                  compliance: dict[str, Any] | None = None) -> PartnerAffiliation:
        if affiliation_kind not in VALID_AFFILIATION_KINDS:
            raise WorkflowError(
                f"Unknown affiliation kind '{affiliation_kind}'. "
                f"Allowed: {', '.join(sorted(VALID_AFFILIATION_KINDS))}"
            )
        row = PartnerAffiliation(
            student_id=student_id, partner_name=partner_name,
            affiliation_kind=affiliation_kind, partner_ref=partner_ref,
            valid_from=valid_from, valid_to=valid_to, compliance=compliance,
            active=True,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def end(self, affiliation_id: uuid.UUID, *, valid_to: date) -> PartnerAffiliation:
        row = (await self.session.execute(
            select(PartnerAffiliation).where(PartnerAffiliation.id == affiliation_id)
        )).scalar_one_or_none()
        if row is None:
            raise NotFoundError("Partner affiliation not found")
        row.valid_to = valid_to
        row.active = False
        await self.session.commit()
        await self.session.refresh(row)
        return row

    @staticmethod
    def compliance_expiry_flags(row: PartnerAffiliation, *,
                                warn_within_days: int = 60) -> list[dict]:
        """Return per-compliance-key flags: ok / expiring / expired."""
        out = []
        if not row.compliance:
            return out
        today = date.today()
        for key, value in (row.compliance or {}).items():
            if not (isinstance(value, str) and (key.endswith("ExpiresOn") or key.endswith("RenewalOn"))):
                continue
            try:
                d = date.fromisoformat(value)
            except ValueError:
                continue
            if d < today:
                out.append({"key": key, "date": value, "status": "expired",
                            "daysOverdue": (today - d).days})
            elif (d - today).days <= warn_within_days:
                out.append({"key": key, "date": value, "status": "expiring",
                            "daysUntil": (d - today).days})
            else:
                out.append({"key": key, "date": value, "status": "ok"})
        return out
