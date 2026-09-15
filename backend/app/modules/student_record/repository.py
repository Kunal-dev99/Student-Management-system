"""Student data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.models import Programme, Student


class StudentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        allowed_ids: list[uuid.UUID] | None = None,
        search: str | None = None,
        status: StudentStatus | None = None,
    ) -> tuple[list[Student], int]:
        # allowed_ids: None = unrestricted; a list (incl. empty) = restrict to those ids (row scoping).
        stmt = select(Student)
        count = select(func.count()).select_from(Student)
        if allowed_ids is not None:
            stmt = stmt.where(Student.id.in_(allowed_ids))
            count = count.where(Student.id.in_(allowed_ids))
        if status is not None:
            stmt = stmt.where(Student.status == status)
            count = count.where(Student.status == status)
        if search:
            # A person's name isn't on the student row — join to search it, same as the
            # register displays it. Matched against ref, given name and family name.
            like = f"%{search.lower()}%"
            cond = or_(
                func.lower(Student.student_ref).like(like),
                func.lower(Person.given_name).like(like),
                func.lower(Person.family_name).like(like),
            )
            stmt = stmt.join(Person, Person.id == Student.person_id).where(cond)
            count = count.join(Person, Person.id == Student.person_id).where(cond)
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

    async def get_by_ref(self, student_ref: str) -> Student | None:
        res = await self.session.execute(select(Student).where(Student.student_ref == student_ref))
        return res.scalars().unique().one_or_none()

    async def first_programme(self) -> Programme | None:
        res = await self.session.execute(select(Programme).limit(1))
        return res.scalar_one_or_none()

    async def list_programmes(self) -> list[Programme]:
        res = await self.session.execute(select(Programme).order_by(Programme.name))
        return list(res.scalars().all())

    async def get_programme(self, programme_id: uuid.UUID) -> Programme | None:
        return (
            await self.session.execute(select(Programme).where(Programme.id == programme_id))
        ).scalar_one_or_none()

    async def get_programme_by_code(self, code: str) -> Programme | None:
        return (
            await self.session.execute(select(Programme).where(Programme.code == code))
        ).scalar_one_or_none()

    async def add(self, student: Student) -> Student:
        self.session.add(student)
        await self.session.flush()
        return student
