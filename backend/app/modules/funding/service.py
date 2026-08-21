"""Funding business rules (arch §8.9).

A funding change closes the current arrangement and opens a new one in one transaction, so a
student's funding history is preserved. (Finance notification via the outbox is Phase 2.)
"""
from __future__ import annotations

import uuid
from datetime import date

from app.core.errors import NotFoundError, WorkflowError
from app.modules.funding.constants import FundingStatus, FundingType
from app.modules.funding.models import FundingArrangement
from app.modules.funding.repository import FundingRepository
from app.modules.funding.schemas import ArrangementCreate, ChangeRequest
from app.modules.student_record.repository import StudentRepository


class FundingService:
    def __init__(self, repo: FundingRepository) -> None:
        self.repo = repo
        self.session = repo.session

    async def list_sources(self):
        return await self.repo.list_sources()

    async def _arrangement_dict(self, a: FundingArrangement, names: dict) -> dict:
        return {
            "id": a.id,
            "studentId": a.student_id,
            "fundingType": a.funding_type,
            "fundingSourceId": a.funding_source_id,
            "fundingSourceName": names.get(a.funding_source_id) if a.funding_source_id else None,
            "stipendAmount": a.stipend_amount,
            "currency": a.currency,
            "validFrom": a.valid_from,
            "validTo": a.valid_to,
            "status": a.status,
            "createdAt": a.created_at,
        }

    async def list_arrangements(self, student_id: uuid.UUID, *, allowed_ids=None) -> list[dict]:
        student = await StudentRepository(self.session).get(student_id, allowed_ids=allowed_ids)
        if student is None:
            raise NotFoundError("Student not found")
        rows = await self.repo.arrangements_for_student(student_id)
        names = await self.repo.source_names()
        return [await self._arrangement_dict(a, names) for a in rows]

    async def create_arrangement(self, student_id: uuid.UUID, data: ArrangementCreate) -> FundingArrangement:
        if await StudentRepository(self.session).get(student_id) is None:
            raise NotFoundError("Student not found")
        arrangement = FundingArrangement(
            student_id=student_id,
            funding_type=data.funding_type,
            funding_source_id=data.funding_source_id,
            stipend_amount=data.stipend_amount,
            currency=data.currency,
            valid_from=data.valid_from or date.today(),
            valid_to=None,
            status=FundingStatus.active,
        )
        self.repo.add(arrangement)
        await self.session.commit()
        await self.session.refresh(arrangement)
        return arrangement

    async def _get(self, arrangement_id: uuid.UUID) -> FundingArrangement:
        a = await self.repo.get(arrangement_id)
        if a is None:
            raise NotFoundError("Funding arrangement not found")
        return a

    async def change(self, arrangement_id: uuid.UUID, data: ChangeRequest) -> FundingArrangement:
        current = await self._get(arrangement_id)
        if current.valid_to is not None:
            raise WorkflowError("This arrangement has already ended; nothing to change")
        # Close current, open new — one transaction (arch §8.9).
        current.valid_to = date.today()
        current.status = FundingStatus.changed
        new = FundingArrangement(
            student_id=current.student_id,
            funding_type=data.funding_type,
            funding_source_id=data.funding_source_id,
            stipend_amount=data.stipend_amount,
            currency=data.currency,
            valid_from=date.today(),
            valid_to=None,
            status=FundingStatus.active,
        )
        self.repo.add(new)
        await self.session.flush()  # populate new.id before referencing it in the event

        # Notify Finance of the funding change via the outbox (arch §8.9, §10.2).
        from app.modules.workflow.engine import WorkflowEngine
        WorkflowEngine(self.session).emit(
            "funding_arrangement", new.id, "funding.changed",
            {"studentId": str(new.student_id), "fundingType": new.funding_type.value},
        )

        await self.session.commit()
        await self.session.refresh(new)
        return new

    async def end_active_for_student(self, student_id: uuid.UUID) -> int:
        """End every active arrangement for a student. Flushes only — caller owns the
        transaction (used by graduation, arch §8.11). Returns how many were ended."""
        count = 0
        for a in await self.repo.arrangements_for_student(student_id):
            if a.valid_to is None:
                a.valid_to = date.today()
                a.status = FundingStatus.ended
                count += 1
        await self.session.flush()
        return count

    async def end(self, arrangement_id: uuid.UUID) -> FundingArrangement:
        a = await self._get(arrangement_id)
        if a.valid_to is None:
            a.valid_to = date.today()
            a.status = FundingStatus.ended
            await self.session.commit()
            await self.session.refresh(a)
        return a
