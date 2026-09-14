"""Funding data access (queries only)."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.funding.constants import PaymentStatus
from app.modules.funding.models import (
    FeeWaiver,
    FundingArrangement,
    FundingSource,
    StipendPayment,
)
from app.modules.person.models import Person
from app.modules.student_record.models import Student


class FundingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_sources(self) -> list[FundingSource]:
        res = await self.session.execute(select(FundingSource).order_by(FundingSource.name))
        return list(res.scalars().all())

    async def source_names(self) -> dict[uuid.UUID, str]:
        return {s.id: s.name for s in await self.list_sources()}

    async def arrangements_for_student(self, student_id: uuid.UUID) -> list[FundingArrangement]:
        res = await self.session.execute(
            select(FundingArrangement)
            .where(FundingArrangement.student_id == student_id)
            .order_by(FundingArrangement.valid_from)
        )
        return list(res.scalars().all())

    async def get(self, arrangement_id: uuid.UUID) -> FundingArrangement | None:
        return (
            await self.session.execute(
                select(FundingArrangement).where(FundingArrangement.id == arrangement_id)
            )
        ).scalar_one_or_none()

    # --- Phase 4B.7 — stipend payments and fee waivers ---
    async def payments_for_arrangement(self, arrangement_id: uuid.UUID) -> list[StipendPayment]:
        res = await self.session.execute(
            select(StipendPayment)
            .where(StipendPayment.arrangement_id == arrangement_id)
            .order_by(StipendPayment.sequence)
        )
        return list(res.scalars().all())

    async def payments_for_student(self, student_id: uuid.UUID) -> list[StipendPayment]:
        res = await self.session.execute(
            select(StipendPayment)
            .where(StipendPayment.student_id == student_id)
            .order_by(StipendPayment.due_date)
        )
        return list(res.scalars().all())

    async def get_payment(self, payment_id: uuid.UUID) -> StipendPayment | None:
        return (await self.session.execute(
            select(StipendPayment).where(StipendPayment.id == payment_id)
        )).scalar_one_or_none()

    async def get_payment_joined(
        self, payment_id: uuid.UUID,
    ) -> tuple[StipendPayment, FundingArrangement, Student, Person] | None:
        """Same join as list_payments(), for one row — so the Payment Status drawer can
        refresh its own payment after an action without depending on it still matching
        whatever filter/search/page the underlying list happens to be on."""
        return (await self.session.execute(
            select(StipendPayment, FundingArrangement, Student, Person)
            .join(FundingArrangement, FundingArrangement.id == StipendPayment.arrangement_id)
            .join(Student, Student.id == StipendPayment.student_id)
            .join(Person, Person.id == Student.person_id)
            .where(StipendPayment.id == payment_id)
        )).first()

    async def list_payments(
        self,
        *,
        limit: int,
        offset: int,
        allowed_ids: list[uuid.UUID] | None = None,
        status: PaymentStatus | None = None,
        search: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> tuple[list[tuple[StipendPayment, FundingArrangement, Student, Person]], int]:
        """Every stipend payment institution-wide — the "Payment Status" page's source query.

        Joined against the arrangement/student/person so the page never needs a second
        round trip per row. Row-scoped like every other funding read.
        """
        stmt = (
            select(StipendPayment, FundingArrangement, Student, Person)
            .join(FundingArrangement, FundingArrangement.id == StipendPayment.arrangement_id)
            .join(Student, Student.id == StipendPayment.student_id)
            .join(Person, Person.id == Student.person_id)
        )
        count_stmt = (
            select(func.count()).select_from(StipendPayment)
            .join(FundingArrangement, FundingArrangement.id == StipendPayment.arrangement_id)
            .join(Student, Student.id == StipendPayment.student_id)
            .join(Person, Person.id == Student.person_id)
        )
        if allowed_ids is not None:
            stmt = stmt.where(StipendPayment.student_id.in_(allowed_ids))
            count_stmt = count_stmt.where(StipendPayment.student_id.in_(allowed_ids))
        if status is not None:
            stmt = stmt.where(StipendPayment.status == status)
            count_stmt = count_stmt.where(StipendPayment.status == status)
        if from_date is not None:
            stmt = stmt.where(StipendPayment.due_date >= from_date)
            count_stmt = count_stmt.where(StipendPayment.due_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(StipendPayment.due_date <= to_date)
            count_stmt = count_stmt.where(StipendPayment.due_date <= to_date)
        if search:
            like = f"%{search.lower()}%"
            cond = or_(
                func.lower(Student.student_ref).like(like),
                func.lower(Person.given_name).like(like),
                func.lower(Person.family_name).like(like),
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        # Oldest/most-overdue first — same "worklist" convention as the Thesis/Completion
        # pipeline pages. Sorting by due_date desc (furthest-future first) buried every
        # instalment with real Finance history under a wall of untouched future-dated
        # "scheduled" rows, which made the page look empty of activity by default.
        stmt = stmt.order_by(StipendPayment.due_date.asc()).limit(limit).offset(offset)
        rows = (await self.session.execute(stmt)).all()
        total = (await self.session.execute(count_stmt)).scalar_one()
        return list(rows), int(total)

    async def waivers_for_student(self, student_id: uuid.UUID) -> list[FeeWaiver]:
        res = await self.session.execute(
            select(FeeWaiver).where(FeeWaiver.student_id == student_id).order_by(FeeWaiver.created_at)
        )
        return list(res.scalars().all())

    def add(self, obj) -> None:
        self.session.add(obj)
