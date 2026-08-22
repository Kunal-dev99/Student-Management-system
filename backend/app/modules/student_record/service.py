"""Student record business rules (arch §6.1, §8.6)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from app.core.errors import ConflictError, NotFoundError
from app.modules.person.repository import PersonRepository
from app.modules.person.service import PersonService
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import ResearchProject, Student
from app.modules.student_record.repository import StudentRepository


def _generate_student_ref() -> str:
    year = datetime.now(timezone.utc).year
    return f"PGR-{year}-{uuid.uuid4().hex[:6].upper()}"


class StudentService:
    def __init__(self, repo: StudentRepository) -> None:
        self.repo = repo

    async def list_students(self, *, limit: int, offset: int, allowed_ids=None):
        return await self.repo.list(limit=limit, offset=offset, allowed_ids=allowed_ids)

    async def get_student(self, student_id: uuid.UUID, *, allowed_ids=None) -> Student:
        student = await self.repo.get(student_id, allowed_ids=allowed_ids)
        if student is None:
            raise NotFoundError("Student not found")
        return student

    async def update_student(self, student_id: uuid.UUID, patch: dict) -> Student:
        student = await self.get_student(student_id)
        for key, value in patch.items():
            setattr(student, key, value)
        await self.repo.session.commit()
        await self.repo.session.refresh(student)
        return student

    async def create_from_application(
        self,
        *,
        person_id: uuid.UUID,
        programme_id: uuid.UUID | None,
        department_id: uuid.UUID | None,
        research_area_id: uuid.UUID | None,
        start_date: date | None,
        study_mode: StudyMode,
        research_topic: str | None,
        research_award_id: uuid.UUID | None = None,
        research_opportunity_id: uuid.UUID | None = None,
    ) -> Student:
        """Create a student, REUSING the applicant's person_id (arch §8.6 key rule)."""
        if await self.repo.get_by_person(person_id) is not None:
            raise ConflictError("This person is already a student")
        if programme_id is None:
            prog = await self.repo.first_programme()
            programme_id = prog.id if prog else None

        student = Student(
            person_id=person_id,
            student_ref=_generate_student_ref(),
            programme_id=programme_id,
            department_id=department_id,
            research_area_id=research_area_id,
            start_date=start_date or date.today(),
            study_mode=study_mode,
            status=StudentStatus.registered,
        )
        # Phase 6.3 — create the research project whenever there is anything to record against it,
        # carrying the award and originating position so the funding lineage works without anyone
        # having to link it by hand later.
        if research_topic or research_award_id or research_opportunity_id:
            student.project = ResearchProject(
                research_topic=research_topic,
                research_area_id=research_area_id,
                research_award_id=research_award_id,
                research_opportunity_id=research_opportunity_id,
                start_date=student.start_date,
            )
        await self.repo.add(student)
        return student

    async def summary(self, student_id: uuid.UUID, *, allowed_ids=None) -> dict:
        from app.modules.funding.repository import FundingRepository
        from app.modules.funding.service import FundingService
        from app.modules.supervision.repository import SupervisionRepository
        from app.modules.supervision.service import SupervisionService

        student = await self.get_student(student_id, allowed_ids=allowed_ids)
        person_service = PersonService(PersonRepository(self.repo.session))
        person = await person_service.get_person(student.person_id)
        supervisors = await SupervisionService(
            SupervisionRepository(self.repo.session)
        ).supervisors_for_student(student_id)
        active = [
            {"name": s["supervisorName"], "role": s["role"].value if hasattr(s["role"], "value") else s["role"]}
            for s in supervisors if s["validTo"] is None
        ]
        arrangements = await FundingService(
            FundingRepository(self.repo.session)
        ).list_arrangements(student_id, allowed_ids=allowed_ids)
        funding = [
            {
                "fundingType": a["fundingType"].value if hasattr(a["fundingType"], "value") else a["fundingType"],
                "stipendAmount": str(a["stipendAmount"]) if a["stipendAmount"] is not None else None,
                "currency": a["currency"],
                "source": a["fundingSourceName"],
            }
            for a in arrangements if a["validTo"] is None
        ]
        return {
            "id": student.id,
            "studentRef": student.student_ref,
            "personId": student.person_id,
            "personName": f"{person.given_name} {person.family_name}",
            "status": student.status,
            "studyMode": student.study_mode,
            "startDate": student.start_date,
            "programmeId": student.programme_id,
            "researchTopic": student.project.research_topic if student.project else None,
            "supervisors": active,
            "funding": funding,
        }
