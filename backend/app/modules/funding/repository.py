"""Funding data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.funding.models import (
    FeeWaiver,
    FundingArrangement,
    FundingSource,
    StipendPayment,
)


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

    async def waivers_for_student(self, student_id: uuid.UUID) -> list[FeeWaiver]:
        res = await self.session.execute(
            select(FeeWaiver).where(FeeWaiver.student_id == student_id).order_by(FeeWaiver.created_at)
        )
        return list(res.scalars().all())

    def add(self, obj) -> None:
        self.session.add(obj)
