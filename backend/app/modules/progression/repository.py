"""Progression data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.progression.models import (
    Milestone,
    MilestoneDefinition,
    ProgressionAppeal,
    ProgressionReview,
    ReviewPanelMember,
)


class ProgressionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def definitions_for_programme(self, programme_id: uuid.UUID) -> list[MilestoneDefinition]:
        rows = await self.session.execute(
            select(MilestoneDefinition)
            .where(MilestoneDefinition.programme_id == programme_id)
            .order_by(MilestoneDefinition.due_offset_days)
        )
        return list(rows.scalars().all())

    async def get_definition(self, def_id: uuid.UUID) -> MilestoneDefinition | None:
        return (
            await self.session.execute(select(MilestoneDefinition).where(MilestoneDefinition.id == def_id))
        ).scalar_one_or_none()

    async def milestones_for_student(self, student_id: uuid.UUID) -> list[Milestone]:
        rows = await self.session.execute(
            select(Milestone).where(Milestone.student_id == student_id).order_by(Milestone.due_date)
        )
        return list(rows.scalars().unique().all())

    async def get_milestone(self, milestone_id: uuid.UUID) -> Milestone | None:
        return (
            await self.session.execute(select(Milestone).where(Milestone.id == milestone_id))
        ).scalars().unique().one_or_none()

    # --- Phase 4B.6 — reviews and appeals ---
    async def get_review(self, review_id: uuid.UUID) -> ProgressionReview | None:
        return (await self.session.execute(
            select(ProgressionReview).where(ProgressionReview.id == review_id)
        )).scalars().unique().one_or_none()

    async def appeals_for_review(self, review_id: uuid.UUID) -> list[ProgressionAppeal]:
        rows = await self.session.execute(
            select(ProgressionAppeal)
            .where(ProgressionAppeal.review_id == review_id)
            .order_by(ProgressionAppeal.submitted_at.desc())
        )
        return list(rows.scalars().all())

    async def panel_members(self, review_id: uuid.UUID) -> list[ReviewPanelMember]:
        """Query members directly — a freshly-flushed review has no loaded collection."""
        rows = await self.session.execute(
            select(ReviewPanelMember)
            .where(ReviewPanelMember.review_id == review_id)
            .order_by(ReviewPanelMember.created_at)
        )
        return list(rows.scalars().all())

    async def get_appeal(self, appeal_id: uuid.UUID) -> ProgressionAppeal | None:
        return (await self.session.execute(
            select(ProgressionAppeal).where(ProgressionAppeal.id == appeal_id)
        )).scalar_one_or_none()

    def add(self, obj) -> None:
        self.session.add(obj)
