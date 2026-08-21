"""Recruitment data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.recruitment.models import Application, ResearchOpportunity


class RecruitmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # Opportunities
    async def list_opportunities(self, *, limit: int, offset: int, status: str | None):
        stmt = select(ResearchOpportunity)
        count = select(func.count()).select_from(ResearchOpportunity)
        if status:
            stmt = stmt.where(ResearchOpportunity.status == status)
            count = count.where(ResearchOpportunity.status == status)
        stmt = stmt.order_by(ResearchOpportunity.created_at.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(stmt)).scalars().all()
        total = (await self.session.execute(count)).scalar_one()
        return list(rows), int(total)

    async def get_opportunity(self, oid: uuid.UUID) -> ResearchOpportunity | None:
        return (
            await self.session.execute(select(ResearchOpportunity).where(ResearchOpportunity.id == oid))
        ).scalar_one_or_none()

    # Applications
    async def list_applications(self, *, limit: int, offset: int, stage: str | None):
        stmt = select(Application)
        count = select(func.count()).select_from(Application)
        if stage:
            stmt = stmt.where(Application.current_stage == stage)
            count = count.where(Application.current_stage == stage)
        stmt = stmt.order_by(Application.created_at.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(stmt)).scalars().unique().all()
        total = (await self.session.execute(count)).scalar_one()
        return list(rows), int(total)

    async def get_application(self, aid: uuid.UUID) -> Application | None:
        return (
            await self.session.execute(select(Application).where(Application.id == aid))
        ).scalars().unique().one_or_none()

    async def pipeline_counts(self) -> dict[str, int]:
        stmt = select(Application.current_stage, func.count()).group_by(Application.current_stage)
        rows = (await self.session.execute(stmt)).all()
        return {stage.value if hasattr(stage, "value") else str(stage): int(n) for stage, n in rows}

    def add(self, obj) -> None:
        self.session.add(obj)
