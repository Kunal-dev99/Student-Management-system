"""Student data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.student_record.models import Programme, Student


class StudentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self, *, limit: int, offset: int, allowed_ids: list[uuid.UUID] | None = None
    ) -> tuple[list[Student], int]:
        # allowed_ids: None = unrestricted; a list (incl. empty) = restrict to those ids (row scoping).
        stmt = select(Student)
        count = select(func.count()).select_from(Student)
        if allowed_ids is not None:
            stmt = stmt.where(Student.id.in_(allowed_ids))
            count = count.where(Student.id.in_(allowed_ids))
        stmt = stmt.order_by(Student.created_at.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(stmt)).scalars().unique().all()
        total = (await self.session.execute(count)).scalar_one()
        return list(rows), int(total)

    async def get(
        self, student_id: uuid.UUID, *, allowed_ids: list[uuid.UUID] | None = None
    ) -> Student | None:
        if allowed_ids is not None and student_id not in allowed_ids:
            return None  # out of scope -> treated as not found (arch §12.3)
        res = await self.session.execute(select(Student).where(Student.id == student_id))
        return res.scalars().unique().one_or_none()

    async def get_by_person(self, person_id: uuid.UUID) -> Student | None:
        res = await self.session.execute(select(Student).where(Student.person_id == person_id))
        return res.scalars().unique().one_or_none()

    async def first_programme(self) -> Programme | None:
        res = await self.session.execute(select(Programme).limit(1))
        return res.scalar_one_or_none()

    async def list_programmes(self) -> list[Programme]:
        res = await self.session.execute(select(Programme).order_by(Programme.name))
        return list(res.scalars().all())

    async def add(self, student: Student) -> Student:
        self.session.add(student)
        await self.session.flush()
        return student
