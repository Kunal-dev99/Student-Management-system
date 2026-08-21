"""Progression business rules (arch §8.8).

On a panel decision, the service records the outcome, updates the milestone, and generates the
next milestone from the programme's definitions (arch §8.8) — a stand-in for the scheduled
generator (§9.3) until the worker tier lands (Phase 2).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from app.core.errors import NotFoundError, WorkflowError
from app.modules.progression.constants import (
    CONTINUING_OUTCOMES,
    MilestoneStatus,
    ProgressionOutcome,
)
from app.modules.progression.models import Milestone, MilestoneDefinition, ProgressionReview
from app.modules.progression.repository import ProgressionRepository
from app.modules.progression.schemas import MilestoneDefinitionCreate
from app.modules.student_record.models import Student
from app.modules.student_record.repository import StudentRepository


class ProgressionService:
    def __init__(self, repo: ProgressionRepository) -> None:
        self.repo = repo
        self.session = repo.session

    # --- Definitions (configuration) ---
    async def list_definitions(self, programme_id: uuid.UUID):
        return await self.repo.definitions_for_programme(programme_id)

    async def create_definition(self, programme_id: uuid.UUID, data: MilestoneDefinitionCreate):
        defn = MilestoneDefinition(programme_id=programme_id, **data.model_dump())
        self.repo.add(defn)
        await self.session.commit()
        await self.session.refresh(defn)
        return defn

    # --- Milestones (instances) ---
    async def _generate_next(self, student: Student) -> Milestone | None:
        """Create a milestone for the next programme definition not yet instantiated."""
        if student.programme_id is None:
            return None
        defs = await self.repo.definitions_for_programme(student.programme_id)
        existing = {m.milestone_definition_id for m in await self.repo.milestones_for_student(student.id)}
        for defn in defs:  # ordered by due_offset_days
            if defn.id not in existing:
                due = (student.start_date or date.today()) + timedelta(days=defn.due_offset_days)
                status = MilestoneStatus.due if due <= date.today() else MilestoneStatus.not_started
                milestone = Milestone(
                    student_id=student.id, milestone_definition_id=defn.id,
                    due_date=due, status=status,
                )
                self.repo.add(milestone)
                await self.session.flush()
                return milestone
        return None

    async def list_milestones(self, student_id: uuid.UUID, *, allowed_ids=None) -> list[dict]:
        student = await StudentRepository(self.session).get(student_id, allowed_ids=allowed_ids)
        if student is None:
            raise NotFoundError("Student not found")
        milestones = await self.repo.milestones_for_student(student_id)
        if not milestones:
            # Lazily generate the first milestone (stands in for the scheduled generator).
            if await self._generate_next(student) is not None:
                await self.session.commit()
                milestones = await self.repo.milestones_for_student(student_id)

        defs = {d.id: d for d in await self.repo.definitions_for_programme(student.programme_id)} if student.programme_id else {}
        return [self._milestone_dict(m, defs.get(m.milestone_definition_id)) for m in milestones]

    def _milestone_dict(self, m: Milestone, defn: MilestoneDefinition | None) -> dict:
        review = None
        if m.review is not None:
            review = {
                "id": m.review.id,
                "studentSubmissionRef": m.review.student_submission_ref,
                "panelDecision": m.review.panel_decision,
                "decidedAt": m.review.decided_at,
                "rationale": m.review.rationale,
            }
        return {
            "id": m.id,
            "studentId": m.student_id,
            "milestoneDefinitionId": m.milestone_definition_id,
            "name": defn.name if defn else "Milestone",
            "dueDate": m.due_date,
            "status": m.status,
            "review": review,
        }

    async def _get_milestone(self, milestone_id: uuid.UUID) -> Milestone:
        m = await self.repo.get_milestone(milestone_id)
        if m is None:
            raise NotFoundError("Milestone not found")
        return m

    def _ensure_review(self, milestone: Milestone) -> ProgressionReview:
        if milestone.review is None:
            milestone.review = ProgressionReview(milestone_id=milestone.id)
        return milestone.review

    async def submit(self, milestone_id: uuid.UUID, submission_ref: str | None) -> Milestone:
        m = await self._get_milestone(milestone_id)
        if m.status == MilestoneStatus.decided:
            raise WorkflowError("Milestone already decided")
        review = self._ensure_review(m)
        review.student_submission_ref = submission_ref
        m.status = MilestoneStatus.submitted

        # Workflow engine: open a review task for the panel/supervisor (arch §9.2).
        from app.modules.workflow.engine import WorkflowEngine
        defn = await self.repo.get_definition(m.milestone_definition_id)
        name = defn.name if defn else "milestone"
        engine = WorkflowEngine(self.session)
        engine.create_task(
            title=f"Review submitted milestone: {name}",
            assignee_role="Supervisor",
            aggregate_type="milestone", aggregate_id=m.id,
            payload={"studentId": str(m.student_id), "milestone": name},
        )
        engine.emit("milestone", m.id, "milestone.submitted", {"studentId": str(m.student_id)})

        await self.session.commit()
        await self.session.refresh(m)
        return m

    async def decide(
        self, milestone_id: uuid.UUID, outcome: ProgressionOutcome, rationale: str | None, user_id
    ) -> tuple[Milestone, Milestone | None]:
        m = await self._get_milestone(milestone_id)
        if m.status == MilestoneStatus.decided:
            raise WorkflowError("Milestone already decided")
        review = self._ensure_review(m)
        review.panel_decision = outcome
        review.rationale = rationale
        review.decided_by_user_id = user_id
        review.decided_at = datetime.now(timezone.utc)
        m.status = MilestoneStatus.decided

        # Notify the student's user of the decision (arch §9 — notification engine).
        from app.modules.identity.repository import IdentityRepository
        from app.modules.workflow.engine import WorkflowEngine

        student = await StudentRepository(self.session).get(m.student_id)
        if student is not None:
            student_user = await IdentityRepository(self.session).get_user_by_person(student.person_id)
            if student_user is not None:
                WorkflowEngine(self.session).notify(
                    recipient_user_id=student_user.id, template="milestone.decided",
                    payload={"milestoneId": str(m.id), "outcome": outcome.value},
                )

        # Continuing outcome -> generate the next milestone (arch §8.8).
        next_milestone = None
        if outcome in CONTINUING_OUTCOMES and student is not None:
            next_milestone = await self._generate_next(student)

        await self.session.commit()
        await self.session.refresh(m)
        return m, next_milestone
