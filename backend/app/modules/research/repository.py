"""Research context data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.research.models import ResearchAward, ResearchDemand


class ResearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- awards ---
    async def list_awards(self, limit: int = 100) -> list[ResearchAward]:
        rows = await self.session.execute(
            select(ResearchAward).order_by(ResearchAward.created_at.desc()).limit(limit)
        )
        return list(rows.scalars().all())

    async def get_award(self, award_id: uuid.UUID) -> ResearchAward | None:
        return (await self.session.execute(
            select(ResearchAward).where(ResearchAward.id == award_id)
        )).scalar_one_or_none()

    async def get_award_by_ref(self, award_ref: str) -> ResearchAward | None:
        return (await self.session.execute(
            select(ResearchAward).where(ResearchAward.award_ref == award_ref)
        )).scalar_one_or_none()

    # --- demand ---
    async def list_demands(self, status: str | None = None, limit: int = 100) -> list[ResearchDemand]:
        stmt = select(ResearchDemand).order_by(ResearchDemand.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(ResearchDemand.status == status)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_demand(self, demand_id: uuid.UUID) -> ResearchDemand | None:
        return (await self.session.execute(
            select(ResearchDemand).where(ResearchDemand.id == demand_id)
        )).scalar_one_or_none()

    def add(self, obj) -> None:
        self.session.add(obj)
