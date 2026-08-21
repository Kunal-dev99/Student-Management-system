"""Admissions business rules (arch §8.5, §8.6).

The marquee flow: accepting an offer converts the applicant to a student REUSING the same
person_id (arch §8.6 key rule) and preserving the person's identity thread. The whole
conversion runs in ONE transaction (student create + identity change + application
conversion + offer update), so it is all-or-nothing.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.admissions.constants import OfferStatus
from app.modules.admissions.models import Offer
from app.modules.admissions.repository import AdmissionsRepository
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.repository import PersonRepository
from app.modules.person.service import PersonService
from app.modules.recruitment.repository import RecruitmentRepository
from app.modules.recruitment.service import RecruitmentService
from app.modules.student_record.constants import StudyMode
from app.modules.student_record.models import Student
from app.modules.student_record.repository import StudentRepository
from app.modules.student_record.service import StudentService


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AdmissionsService:
    def __init__(self, repo: AdmissionsRepository) -> None:
        self.repo = repo
        self.session = repo.session

    async def _get_offer(self, offer_id: uuid.UUID) -> Offer:
        offer = await self.repo.get_offer(offer_id)
        if offer is None:
            raise NotFoundError("Offer not found")
        return offer

    async def offer_for_application(self, application_id: uuid.UUID) -> Offer | None:
        return await self.repo.get_offer_for_application(application_id)

    async def create_offer(self, application_id: uuid.UUID, conditions: dict | None) -> Offer:
        # Ensure the application exists (service boundary).
        await RecruitmentService(RecruitmentRepository(self.session)).get_application(application_id)
        if await self.repo.get_offer_for_application(application_id) is not None:
            raise ConflictError("An offer already exists for this application")
        offer = Offer(application_id=application_id, status=OfferStatus.draft, conditions=conditions)
        self.repo.add(offer)
        await self.session.commit()
        await self.session.refresh(offer)
        return offer

    async def issue_offer(self, offer_id: uuid.UUID) -> Offer:
        offer = await self._get_offer(offer_id)
        if offer.status != OfferStatus.draft:
            raise WorkflowError(f"Only a draft offer can be issued (currently {offer.status.value})")
        offer.status = OfferStatus.issued
        offer.issued_at = _now()
        await self.session.commit()
        await self.session.refresh(offer)
        return offer

    async def decline_offer(self, offer_id: uuid.UUID) -> Offer:
        offer = await self._get_offer(offer_id)
        if offer.status != OfferStatus.issued:
            raise WorkflowError("Only an issued offer can be declined")
        offer.status = OfferStatus.declined
        offer.responded_at = _now()
        await self.session.commit()
        await self.session.refresh(offer)
        return offer

    async def accept_offer(
        self,
        offer_id: uuid.UUID,
        *,
        programme_id: uuid.UUID | None,
        study_mode: StudyMode,
        start_date,
        user_id: uuid.UUID | None,
    ) -> Student:
        offer = await self._get_offer(offer_id)
        if offer.status != OfferStatus.issued:
            raise WorkflowError(f"Only an issued offer can be accepted (currently {offer.status.value})")

        rec_repo = RecruitmentRepository(self.session)
        rec_svc = RecruitmentService(rec_repo)
        application = await rec_svc.get_application(offer.application_id)

        # Derive department / research area from the opportunity when opportunity-led.
        department_id = None
        research_area_id = application.research_area_id
        if application.research_opportunity_id:
            opp = await rec_repo.get_opportunity(application.research_opportunity_id)
            if opp:
                department_id = opp.department_id
                research_area_id = research_area_id or opp.research_area_id

        # 1) Create the student, REUSING the applicant's person_id.
        student = await StudentService(StudentRepository(self.session)).create_from_application(
            person_id=application.person_id,
            programme_id=programme_id,
            department_id=department_id,
            research_area_id=research_area_id,
            start_date=start_date,
            study_mode=study_mode,
            research_topic=None,
        )
        # 2) Preserve the identity thread: end applicant, open student (same person).
        await PersonService(PersonRepository(self.session)).transition_identity(
            application.person_id,
            end_type=PersonRelationshipType.applicant,
            open_type=PersonRelationshipType.student,
            source_system="admissions",
        )
        # 3) Update offer + application in the same transaction.
        offer.status = OfferStatus.accepted
        offer.responded_at = _now()
        await rec_svc.mark_converted(application, user_id)

        # 4) Workflow engine: onboarding task + domain event, same transaction (arch §9.2/§9.4).
        from app.modules.workflow.engine import WorkflowEngine
        engine = WorkflowEngine(self.session)
        engine.create_task(
            title=f"Onboard new student {student.student_ref}",
            assignee_role="PGR Administrator",
            aggregate_type="student", aggregate_id=student.id,
            payload={"studentRef": student.student_ref},
        )
        engine.emit("student", student.id, "offer.accepted", {"offerId": str(offer.id)})

        await self.session.commit()
        await self.session.refresh(student)
        return student
