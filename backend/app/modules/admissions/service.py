"""Admissions business rules (arch §8.5, §8.6).

The marquee flow: accepting an offer converts the applicant to a student REUSING the same
person_id (arch §8.6 key rule) and preserving the person's identity thread. The whole
conversion runs in ONE transaction (student create + identity change + application
conversion + offer update), so it is all-or-nothing.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.admissions.constants import OfferStatus
from app.modules.admissions.models import Offer
from app.modules.admissions.repository import AdmissionsRepository
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.repository import PersonRepository
from app.modules.person.service import PersonService
from app.modules.recruitment.constants import OpportunityStatus
from app.modules.recruitment.repository import RecruitmentRepository
from app.modules.recruitment.service import RecruitmentService
from app.modules.student_record.constants import PART_TIME_FACTOR, StudyMode
from app.modules.student_record.models import Student
from app.modules.student_record.repository import StudentRepository
from app.modules.student_record.service import StudentService


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _add_months(d, months: int):
    """Add whole months, clamping to the target month's length (e.g. 31 Jan + 1 = 28/29 Feb)."""
    from datetime import date as _date

    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    last = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return _date(year, month, min(d.day, last))


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

        # F3 — visa gate. If the applicant is visa-required, the check must have been completed
        # before Admissions issues the offer. This prevents UKVI compliance drift.
        from app.modules.recruitment.models import Application

        application = (await self.session.execute(
            select(Application).where(Application.id == offer.application_id)
        )).scalar_one_or_none()
        if application is not None and application.visa_required and application.visa_check_completed_at is None:
            raise WorkflowError(
                "This applicant is flagged as visa-required — complete the visa check before issuing "
                "the offer."
            )

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

    async def _mark_demand_filled_if_complete(self, opportunity) -> None:
        """When every position answering a demand is full, the demand itself is satisfied."""
        if not opportunity.research_demand_id:
            return
        from sqlalchemy import select

        from app.modules.recruitment.models import ResearchOpportunity
        from app.modules.research.constants import DemandStatus
        from app.modules.research.models import ResearchDemand

        siblings = (await self.session.execute(
            select(ResearchOpportunity).where(
                ResearchOpportunity.research_demand_id == opportunity.research_demand_id
            )
        )).scalars().all()
        if any(o.positions_filled < o.positions_available for o in siblings):
            return
        demand = (await self.session.execute(
            select(ResearchDemand).where(ResearchDemand.id == opportunity.research_demand_id)
        )).scalar_one_or_none()
        if demand is not None and demand.status is DemandStatus.positioned:
            demand.status = DemandStatus.filled

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

        # F3 — cannot accept while any first-class OfferCondition remains unsatisfied.
        from app.modules.recruitment.f3_service import OfferConditionService

        pending = await OfferConditionService(self.session).any_unsatisfied(offer.id)
        if pending:
            raise WorkflowError(
                f"{len(pending)} offer condition(s) unsatisfied — mark them satisfied or waived "
                f"before accepting. First: {pending[0].description[:80]}"
            )

        rec_repo = RecruitmentRepository(self.session)
        rec_svc = RecruitmentService(rec_repo)
        application = await rec_svc.get_application(offer.application_id)

        # Derive department / research area from the opportunity when opportunity-led.
        department_id = None
        research_area_id = application.research_area_id
        opp = None
        if application.research_opportunity_id:
            opp = await rec_repo.get_opportunity(application.research_opportunity_id)
            if opp:
                department_id = opp.department_id
                research_area_id = research_area_id or opp.research_area_id
                # Phase 6.1 — a position has a finite number of places.
                if opp.positions_filled >= opp.positions_available:
                    raise ConflictError(
                        f"'{opp.title}' is already full "
                        f"({opp.positions_filled}/{opp.positions_available} places taken)"
                    )

        # 1) Create the student, REUSING the applicant's person_id.
        student = await StudentService(StudentRepository(self.session)).create_from_application(
            person_id=application.person_id,
            programme_id=programme_id,
            department_id=department_id,
            research_area_id=research_area_id,
            start_date=start_date,
            study_mode=study_mode,
            research_topic=None,
            # Carry the position's award through, so funding lineage is populated from day one.
            research_award_id=opp.research_award_id if opp else None,
            research_opportunity_id=opp.id if opp else None,
        )
        # Phase 6.1 — derive the expected end date from the position's advertised duration, so
        # there is a baseline for suspensions/extensions to adjust (Phase 6.5 found it missing).
        if opp and opp.expected_duration_months and student.start_date:
            months = opp.expected_duration_months
            if study_mode is StudyMode.part_time:
                months = int(months * PART_TIME_FACTOR)
            student.expected_end_date = _add_months(student.start_date, months)
            student.original_expected_end_date = student.expected_end_date
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

        # Phase 6.1 — take a place, and close the position once it is full so it stops recruiting.
        if opp is not None:
            opp.positions_filled += 1
            if opp.positions_filled >= opp.positions_available:
                if opp.status in (OpportunityStatus.open, OpportunityStatus.recruiting):
                    opp.status = OpportunityStatus.filled
                await self._mark_demand_filled_if_complete(opp)

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
