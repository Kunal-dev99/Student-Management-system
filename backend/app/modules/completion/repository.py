"""Completion data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.completion.models import Award, Completion


class CompletionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_student(self, student_id: uuid.UUID) -> Completion | None:
        return (
            await self.session.execute(select(Completion).where(Completion.student_id == student_id))
        ).scalar_one_or_none()

    async def get_award_by_student(self, student_id: uuid.UUID) -> Award | None:
        return (
            await self.session.execute(
                select(Award).where(Award.student_id == student_id).order_by(Award.created_at.desc())
            )
        ).scalars().first()

    def add(self, obj) -> None:
        self.session.add(obj)
