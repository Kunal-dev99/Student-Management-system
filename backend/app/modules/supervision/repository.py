"""Supervision data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.supervision.models import SupervisorRelationship


class SupervisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_student(self, student_id: uuid.UUID) -> list[SupervisorRelationship]:
        rows = await self.session.execute(
            select(SupervisorRelationship)
            .where(SupervisorRelationship.student_id == student_id)
            .order_by(SupervisorRelationship.valid_from)
        )
        return list(rows.scalars().all())

    async def get(self, rel_id: uuid.UUID) -> SupervisorRelationship | None:
        return (
            await self.session.execute(
                select(SupervisorRelationship).where(SupervisorRelationship.id == rel_id)
            )
        ).scalar_one_or_none()

    async def active_for_supervisor(self, person_id: uuid.UUID) -> list[SupervisorRelationship]:
        rows = await self.session.execute(
            select(SupervisorRelationship).where(
                SupervisorRelationship.supervisor_person_id == person_id,
                SupervisorRelationship.valid_to.is_(None),
            )
        )
        return list(rows.scalars().all())

    async def active_student_ids_for_supervisor(self, person_id: uuid.UUID) -> list[uuid.UUID]:
        rows = await self.session.execute(
            select(SupervisorRelationship.student_id).where(
                SupervisorRelationship.supervisor_person_id == person_id,
                SupervisorRelationship.valid_to.is_(None),
            )
        )
        return [r[0] for r in rows.all()]

    def add(self, rel: SupervisorRelationship) -> None:
        self.session.add(rel)
