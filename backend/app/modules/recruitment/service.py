"""Recruitment business rules (arch §6.1, §8.4). Services own transactions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.errors import NotFoundError, ValidationAppError, WorkflowError
from app.modules.person.repository import PersonRepository
from app.modules.person.service import PersonService
from app.modules.recruitment.constants import (
    OPPORTUNITY_TRANSITIONS,
    TERMINAL_STAGES,
    ApplicationRoute,
    CandidateStage,
    OpportunityStatus,
)
from app.modules.recruitment.models import (
    Application,
    ApplicationAssessment,
    CandidateStageHistory,
    ResearchOpportunity,
)
from app.modules.recruitment.repository import RecruitmentRepository
from app.modules.recruitment.schemas import (
    ApplicationCreate,
    OpportunityCreate,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RecruitmentService:
    def __init__(self, repo: RecruitmentRepository) -> None:
        self.repo = repo

    # --- Opportunities ---
    async def list_opportunities(self, *, limit, offset, status):
        return await self.repo.list_opportunities(limit=limit, offset=offset, status=status)

    async def get_opportunity(self, oid: uuid.UUID) -> ResearchOpportunity:
        opp = await self.repo.get_opportunity(oid)
        if opp is None:
            raise NotFoundError("Opportunity not found")
        return opp

    async def create_opportunity(self, data: OpportunityCreate) -> ResearchOpportunity:
        opp = ResearchOpportunity(**data.model_dump())
        self.repo.add(opp)
        await self.repo.session.commit()
        await self.repo.session.refresh(opp)
        return opp

    async def update_opportunity(self, oid: uuid.UUID, patch: dict) -> ResearchOpportunity:
        opp = await self.get_opportunity(oid)
        for k, v in patch.items():
            setattr(opp, k, v)
        await self.repo.session.commit()
        await self.repo.session.refresh(opp)
        return opp

    async def transition_opportunity(
        self, oid: uuid.UUID, to_status: OpportunityStatus
    ) -> ResearchOpportunity:
        opp = await self.get_opportunity(oid)
        allowed = OPPORTUNITY_TRANSITIONS.get(opp.status, set())
        if to_status not in allowed:
            raise WorkflowError(
                f"Cannot move opportunity from {opp.status.value} to {to_status.value}"
            )
        opp.status = to_status
        await self.repo.session.commit()
        await self.repo.session.refresh(opp)
        return opp

    # --- Applications ---
    async def list_applications(self, *, limit, offset, stage):
        return await self.repo.list_applications(limit=limit, offset=offset, stage=stage)

    async def get_application(self, aid: uuid.UUID) -> Application:
        app = await self.repo.get_application(aid)
        if app is None:
            raise NotFoundError("Application not found")
        return app

    async def create_application(self, data: ApplicationCreate) -> Application:
        # Ensure the person exists (service-to-service, arch §6.1).
        await PersonService(PersonRepository(self.repo.session)).get_person(data.person_id)
        # Phase 6.0 — route integrity (CIO vision: two distinct entry routes).
        # Route A (opportunity_led) starts from an advertised PGR position; Route B (student_led)
        # starts from a person and their own research proposal. Each must carry its own evidence,
        # so the route a student took stays provable later in reporting.
        if data.route == ApplicationRoute.opportunity_led:
            if data.research_opportunity_id is None:
                raise ValidationAppError(
                    "An opportunity-led application must reference a research opportunity"
                )
            opportunity = await self.repo.get_opportunity(data.research_opportunity_id)
            if opportunity is None:
                raise NotFoundError("Research opportunity not found")
        else:  # student_led
            if data.research_opportunity_id is not None:
                raise ValidationAppError(
                    "A student-led application must not reference a research opportunity"
                )
            if data.research_area_id is None and not (data.proposal_document_ref or "").strip():
                raise ValidationAppError(
                    "A student-led application needs a research area or a research proposal"
                )
        app = Application(
            person_id=data.person_id,
            route=data.route,
            research_opportunity_id=data.research_opportunity_id,
            research_area_id=data.research_area_id,
            proposal_document_ref=data.proposal_document_ref,
            current_stage=CandidateStage.applicant,
            submitted_at=_now(),
        )
        app.history.append(
            CandidateStageHistory(from_stage=None, to_stage=CandidateStage.applicant, moved_at=_now())
        )
        self.repo.add(app)
        await self.repo.session.commit()
        await self.repo.session.refresh(app)
        return app

    async def advance(
        self, aid: uuid.UUID, to_stage: CandidateStage, reason: str | None, user_id: uuid.UUID | None
    ) -> Application:
        app = await self.get_application(aid)
        if app.current_stage in TERMINAL_STAGES:
            raise WorkflowError(f"Application is in terminal stage {app.current_stage.value}")
        if to_stage == app.current_stage:
            raise WorkflowError("Application is already in that stage")
        app.history.append(
            CandidateStageHistory(
                from_stage=app.current_stage, to_stage=to_stage, reason=reason,
                moved_by_user_id=user_id, moved_at=_now(),
            )
        )
        app.current_stage = to_stage
        await self.repo.session.commit()
        await self.repo.session.refresh(app)
        return app

    async def assess(
        self, aid: uuid.UUID, *, decision: str, rationale: str | None,
        criteria: dict | None, user_id: uuid.UUID | None,
    ) -> Application:
        app = await self.get_application(aid)
        app.assessments.append(
            ApplicationAssessment(
                assessor_user_id=user_id, decision=decision, rationale=rationale,
                criteria=criteria, assessed_at=_now(),
            )
        )
        # Move to under_assessment if still fresh.
        if app.current_stage == CandidateStage.applicant:
            app.history.append(
                CandidateStageHistory(
                    from_stage=app.current_stage, to_stage=CandidateStage.under_assessment,
                    moved_by_user_id=user_id, moved_at=_now(), reason="assessment recorded",
                )
            )
            app.current_stage = CandidateStage.under_assessment
        await self.repo.session.commit()
        await self.repo.session.refresh(app)
        return app

    async def mark_converted(self, application: Application, user_id: uuid.UUID | None) -> None:
        """Move an application to `converted` on offer acceptance. Flushes only — the caller
        (admissions.accept_offer) owns the transaction so conversion is atomic."""
        application.history.append(
            CandidateStageHistory(
                from_stage=application.current_stage, to_stage=CandidateStage.converted,
                moved_by_user_id=user_id, moved_at=_now(), reason="offer accepted",
            )
        )
        application.current_stage = CandidateStage.converted
        await self.repo.session.flush()

    async def pipeline(self) -> tuple[dict[str, int], int]:
        counts = await self.repo.pipeline_counts()
        return counts, sum(counts.values())
