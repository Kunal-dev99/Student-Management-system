"""Funding data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.funding.models import FundingArrangement, FundingSource


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

    def add(self, obj) -> None:
        self.session.add(obj)
