"""Person data access (queries only — arch §6.1)."""
from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.person.models import Person


class PersonRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self, *, limit: int, offset: int, search: str | None
    ) -> tuple[list[Person], int]:
        stmt = select(Person)
        count_stmt = select(func.count()).select_from(Person)
        if search:
            like = f"%{search.lower()}%"
            cond = or_(
                func.lower(Person.given_name).like(like),
                func.lower(Person.family_name).like(like),
                func.lower(Person.email).like(like),
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        stmt = stmt.order_by(Person.family_name, Person.given_name).limit(limit).offset(offset)
        rows = (await self.session.execute(stmt)).scalars().unique().all()
        total = (await self.session.execute(count_stmt)).scalar_one()
        return list(rows), int(total)

    async def get(self, person_id: uuid.UUID) -> Person | None:
        res = await self.session.execute(select(Person).where(Person.id == person_id))
        return res.scalars().unique().one_or_none()

    async def add(self, person: Person) -> Person:
        self.session.add(person)
        await self.session.flush()
        return person
