"""Thesis data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.thesis.models import ExaminerNomination, Thesis


class ThesisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_student(self, student_id: uuid.UUID) -> Thesis | None:
        return (
            await self.session.execute(select(Thesis).where(Thesis.student_id == student_id))
        ).scalars().unique().one_or_none()

    async def get(self, thesis_id: uuid.UUID) -> Thesis | None:
        return (
            await self.session.execute(select(Thesis).where(Thesis.id == thesis_id))
        ).scalars().unique().one_or_none()

    async def nominations_for_thesis(self, thesis_id: uuid.UUID) -> list[ExaminerNomination]:
        stmt = select(ExaminerNomination).where(ExaminerNomination.thesis_id == thesis_id).order_by(ExaminerNomination.created_at)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_nomination(self, nomination_id: uuid.UUID) -> ExaminerNomination | None:
        return (await self.session.execute(select(ExaminerNomination).where(ExaminerNomination.id == nomination_id))).scalar_one_or_none()

    def add(self, obj) -> None:
        self.session.add(obj)
