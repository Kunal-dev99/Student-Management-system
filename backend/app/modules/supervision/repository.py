"""Supervision data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.supervision.models import SupervisionMeeting, SupervisorRelationship


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

    async def count_active_for_supervisor(self, person_id: uuid.UUID) -> int:
        rows = await self.active_student_ids_for_supervisor(person_id)
        return len(set(rows))

    # --- Phase 4B.5 meeting log ---
    async def meetings_for_student(self, student_id: uuid.UUID) -> list[SupervisionMeeting]:
        rows = await self.session.execute(
            select(SupervisionMeeting)
            .where(SupervisionMeeting.student_id == student_id)
            .order_by(SupervisionMeeting.met_on.desc())
        )
        return list(rows.scalars().all())

    async def last_meeting_for_student(self, student_id: uuid.UUID) -> SupervisionMeeting | None:
        rows = await self.session.execute(
            select(SupervisionMeeting)
            .where(SupervisionMeeting.student_id == student_id)
            .order_by(SupervisionMeeting.met_on.desc())
            .limit(1)
        )
        return rows.scalars().first()

    async def get_meeting(self, meeting_id: uuid.UUID) -> SupervisionMeeting | None:
        return (await self.session.execute(
            select(SupervisionMeeting).where(SupervisionMeeting.id == meeting_id)
        )).scalar_one_or_none()

    def add(self, rel) -> None:
        self.session.add(rel)
