"""Completion business rules (arch §8.11).

Graduation is the lifecycle's closing orchestration and runs in ONE transaction: it records the
award, closes funding, sets the student to completed, and opens an `alumni` relationship on the
SAME person (closing the applicant→student→alumni thread). All-or-nothing.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from app.core.errors import NotFoundError, WorkflowError
from app.modules.completion.constants import CompletionStatus
from app.modules.completion.models import Award, Completion
from app.modules.completion.repository import CompletionRepository
from app.modules.funding.repository import FundingRepository
from app.modules.funding.service import FundingService
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.repository import PersonRepository
from app.modules.person.service import PersonService
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.repository import StudentRepository
from app.modules.thesis.constants import ThesisStatus
from app.modules.thesis.repository import ThesisRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CompletionService:
    def __init__(self, repo: CompletionRepository) -> None:
        self.repo = repo
        self.session = repo.session

    async def _dict(self, completion: Completion, award: Award | None) -> dict:
        return {
            "id": completion.id,
            "studentId": completion.student_id,
            "status": completion.status,
            "requirementsMetAt": completion.requirements_met_at,
            "awardConfirmedAt": completion.award_confirmed_at,
            "graduationDate": completion.graduation_date,
            "award": {
                "id": award.id, "title": award.title,
                "awardType": award.award_type, "conferredAt": award.conferred_at,
            } if award else None,
        }

    async def get_for_student(self, student_id: uuid.UUID, *, allowed_ids=None) -> dict | None:
        student = await StudentRepository(self.session).get(student_id, allowed_ids=allowed_ids)
        if student is None:
            raise NotFoundError("Student not found")
        completion = await self.repo.get_by_student(student_id)
        if completion is None:
            return None
        award = await self.repo.get_award_by_student(student_id)
        return await self._dict(completion, award)

    async def confirm(self, student_id: uuid.UUID) -> dict:
        if await StudentRepository(self.session).get(student_id) is None:
            raise NotFoundError("Student not found")
        thesis = await ThesisRepository(self.session).get_by_student(student_id)
        if thesis is None or thesis.status != ThesisStatus.approved:
            raise WorkflowError("Thesis must be approved before completion can be confirmed")

        completion = await self.repo.get_by_student(student_id)
        if completion is None:
            completion = Completion(student_id=student_id)
            self.repo.add(completion)
        completion.status = CompletionStatus.award_confirmed
        completion.requirements_met_at = _now()
        completion.award_confirmed_at = _now()
        await self.session.commit()
        await self.session.refresh(completion)
        return await self._dict(completion, None)

    async def graduate(self, student_id: uuid.UUID) -> dict:
        student = await StudentRepository(self.session).get(student_id)
        if student is None:
            raise NotFoundError("Student not found")
        completion = await self.repo.get_by_student(student_id)
        if completion is None or completion.status != CompletionStatus.award_confirmed:
            raise WorkflowError("Completion must be award-confirmed before graduation")

        # 1) Completion + award.
        completion.status = CompletionStatus.graduated
        completion.graduation_date = date.today()
        award = Award(student_id=student_id, title="Doctor of Philosophy", award_type="PhD", conferred_at=_now())
        self.repo.add(award)

        # 2) Close funding.
        await FundingService(FundingRepository(self.session)).end_active_for_student(student_id)

        # 3) Student -> completed.
        student.status = StudentStatus.completed

        # 4) Person: end student identity, open alumni (same person — closes the loop, arch §8.11).
        await PersonService(PersonRepository(self.session)).transition_identity(
            student.person_id,
            end_type=PersonRelationshipType.student,
            open_type=PersonRelationshipType.alumni,
            source_system="completion",
        )

        # 5) Emit graduation event (Finance closes funding, HR gains an alumni) via the outbox.
        from app.modules.workflow.engine import WorkflowEngine
        WorkflowEngine(self.session).emit(
            "student", student.id, "student.graduated", {"personId": str(student.person_id)},
        )

        await self.session.commit()
        await self.session.refresh(completion)
        return await self._dict(completion, award)
