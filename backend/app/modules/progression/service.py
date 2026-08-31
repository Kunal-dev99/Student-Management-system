"""Progression business rules (arch §8.8).

On a panel decision, the service records the outcome, updates the milestone, and generates the
next milestone from the programme's definitions (arch §8.8) — a stand-in for the scheduled
generator (§9.3) until the worker tier lands (Phase 2).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.progression.constants import (
    APPEAL_WINDOW_DAYS,
    CONDITIONAL_OUTCOMES,
    CONTINUING_OUTCOMES,
    RE_REVIEW_DAYS,
    REQUIRED_PANEL_ROLES,
    AppealStatus,
    MilestoneStatus,
    PanelRole,
    ProgressionOutcome,
)
from app.modules.progression.models import (
    Milestone,
    MilestoneDefinition,
    ProgressionAppeal,
    ProgressionReview,
    ReviewPanelMember,
)
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

    # --- Phase 4B.6 — review panel membership ---

    async def panel_for_milestone(self, milestone_id: uuid.UUID) -> list[dict]:
        m = await self._get_milestone(milestone_id)
        if m.review is None:
            return []
        from app.modules.person.repository import PersonRepository
        from app.modules.person.service import PersonService

        person_service = PersonService(PersonRepository(self.session))
        out = []
        for member in await self.repo.panel_members(m.review.id):
            p = await person_service.get_person(member.person_id)
            out.append({
                "id": str(member.id), "personId": str(member.person_id),
                "personName": f"{p.given_name} {p.family_name}",
                "role": member.role.value if hasattr(member.role, "value") else member.role,
                "isIndependent": member.is_independent,
            })
        return out

    async def add_panel_member(
        self, milestone_id: uuid.UUID, person_id: uuid.UUID, role: PanelRole, is_independent: bool
    ) -> list[dict]:
        from app.modules.person.repository import PersonRepository
        from app.modules.person.service import PersonService

        m = await self._get_milestone(milestone_id)
        if m.status == MilestoneStatus.decided:
            raise WorkflowError("Cannot change the panel after the decision")
        await PersonService(PersonRepository(self.session)).get_person(person_id)
        review = self._ensure_review(m)
        await self.session.flush()  # review needs an id before members reference it
        for member in await self.repo.panel_members(review.id):
            if member.person_id == person_id:
                raise ConflictError("That person is already on this panel")
        # An independent assessor must not be one of the student's supervisors.
        if role == PanelRole.independent_assessor or is_independent:
            from app.modules.supervision.repository import SupervisionRepository

            sup_ids = {
                r.supervisor_person_id
                for r in await SupervisionRepository(self.session).list_for_student(m.student_id)
                if r.valid_to is None
            }
            if person_id in sup_ids:
                raise WorkflowError("The independent assessor cannot be one of the student's supervisors")
            is_independent = True
        self.session.add(ReviewPanelMember(
            review_id=review.id, person_id=person_id, role=role, is_independent=is_independent,
        ))
        await self.session.commit()
        return await self.panel_for_milestone(milestone_id)

    async def _validate_panel(self, review: ProgressionReview) -> None:
        await self.session.flush()  # a just-created review needs an id to query members
        roles = {m.role for m in await self.repo.panel_members(review.id)}
        missing = REQUIRED_PANEL_ROLES - roles
        if missing:
            names = ", ".join(sorted(r.value for r in missing))
            raise WorkflowError(f"Panel is incomplete — missing: {names}")

    async def decide(
        self, milestone_id: uuid.UUID, outcome: ProgressionOutcome, rationale: str | None, user_id,
        *, conditions: str | None = None, outcome_letter: str | None = None,
        require_panel: bool | None = None,
    ) -> tuple[Milestone, Milestone | None]:
        m = await self._get_milestone(milestone_id)
        if m.status == MilestoneStatus.decided:
            raise WorkflowError("Milestone already decided")
        review = self._ensure_review(m)
        # Phase 4B.6 — a formal review requires a properly constituted panel. Whether this
        # milestone is a formal review is configuration, not a hard-coded rule: the programme's
        # milestone_definition.review_panel says so (e.g. {"required": true}). An explicit
        # require_panel from the caller overrides.
        if require_panel is None:
            defn = await self.repo.get_definition(m.milestone_definition_id)
            panel_cfg = (defn.review_panel if defn else None) or {}
            require_panel = bool(panel_cfg.get("required", False))
        if require_panel:
            await self._validate_panel(review)
        if outcome in CONDITIONAL_OUTCOMES and not (conditions or "").strip():
            raise WorkflowError(f"Outcome '{outcome.value}' requires written conditions")
        review.panel_decision = outcome
        review.rationale = rationale
        review.conditions = conditions
        review.outcome_letter = outcome_letter
        review.decided_by_user_id = user_id
        review.decided_at = datetime.now(timezone.utc)
        review.appeal_deadline = date.today() + timedelta(days=APPEAL_WINDOW_DAYS)
        if outcome in CONDITIONAL_OUTCOMES:
            review.re_review_due = date.today() + timedelta(days=RE_REVIEW_DAYS)
        m.status = MilestoneStatus.decided

        # ICR gap 1 — automatic registration_status flip. The milestone definition may carry a
        # ``registration_effect`` block (e.g. Transfer Viva on the ICR-PHD programme has
        # {"onDecideContinue": "PhD (upgraded)", "onDecideFail": "Withdrawn"}). If it does,
        # the student's registration_status flips to match the outcome bucket. Nothing happens
        # for milestone definitions without the effect — every non-ICR milestone is unaffected.
        defn_for_effect = await self.repo.get_definition(m.milestone_definition_id)
        effect = (defn_for_effect.registration_effect if defn_for_effect else None) or {}
        if effect:
            student_for_flip = await StudentRepository(self.session).get(m.student_id)
            if student_for_flip is not None:
                if outcome in CONTINUING_OUTCOMES and effect.get("onDecideContinue"):
                    student_for_flip.registration_status = effect["onDecideContinue"]
                elif outcome not in CONTINUING_OUTCOMES and effect.get("onDecideFail"):
                    student_for_flip.registration_status = effect["onDecideFail"]

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

    # --- Phase 4B.6 — conditions sign-off + appeals ---

    async def review_detail(self, milestone_id: uuid.UUID) -> dict:
        m = await self._get_milestone(milestone_id)
        r = m.review
        if r is None:
            return {"milestoneId": str(milestone_id), "decided": False, "panel": []}
        return {
            "milestoneId": str(milestone_id),
            "reviewId": str(r.id),
            "decided": r.panel_decision is not None,
            "panelDecision": r.panel_decision.value if r.panel_decision else None,
            "rationale": r.rationale,
            "conditions": r.conditions,
            "reReviewDue": r.re_review_due.isoformat() if r.re_review_due else None,
            "conditionsMet": r.conditions_met_at is not None,
            "outcomeLetter": r.outcome_letter,
            "appealDeadline": r.appeal_deadline.isoformat() if r.appeal_deadline else None,
            "panel": await self.panel_for_milestone(milestone_id),
        }

    async def sign_off_conditions(self, milestone_id: uuid.UUID) -> dict:
        m = await self._get_milestone(milestone_id)
        if m.review is None or m.review.panel_decision is None:
            raise WorkflowError("This milestone has no decision yet")
        if not m.review.conditions:
            raise WorkflowError("This decision carried no conditions")
        if m.review.conditions_met_at is not None:
            raise ConflictError("Conditions are already signed off")
        m.review.conditions_met_at = datetime.now(timezone.utc)
        await self.session.commit()
        return await self.review_detail(milestone_id)

    async def submit_appeal(self, milestone_id: uuid.UUID, grounds: str) -> dict:
        m = await self._get_milestone(milestone_id)
        if m.review is None or m.review.panel_decision is None:
            raise WorkflowError("There is no decision to appeal")
        if not (grounds or "").strip():
            raise WorkflowError("Appeal grounds are required")
        if m.review.appeal_deadline and date.today() > m.review.appeal_deadline:
            raise WorkflowError("The appeal window for this decision has closed")
        existing = await self.repo.appeals_for_review(m.review.id)
        if any(a.status in (AppealStatus.submitted, AppealStatus.under_review) for a in existing):
            raise ConflictError("An appeal is already in progress for this decision")
        appeal = ProgressionAppeal(
            review_id=m.review.id, student_id=m.student_id, grounds=grounds,
            status=AppealStatus.submitted, submitted_at=datetime.now(timezone.utc),
        )
        self.session.add(appeal)

        # Open an administrative task to consider the appeal (arch §9.2).
        from app.modules.workflow.engine import WorkflowEngine

        await self.session.flush()
        WorkflowEngine(self.session).create_task(
            title="Consider progression appeal",
            assignee_role="PGR Administrator",
            aggregate_type="progression_appeal", aggregate_id=appeal.id,
            payload={"studentId": str(m.student_id), "milestoneId": str(m.id)},
        )
        await self.session.commit()
        await self.session.refresh(appeal)
        return self._appeal_out(appeal)

    def _appeal_out(self, a: ProgressionAppeal) -> dict:
        return {
            "id": str(a.id), "reviewId": str(a.review_id), "studentId": str(a.student_id),
            "grounds": a.grounds,
            "status": a.status.value if hasattr(a.status, "value") else a.status,
            "submittedAt": a.submitted_at.isoformat() if a.submitted_at else None,
            "decidedAt": a.decided_at.isoformat() if a.decided_at else None,
            "decisionNote": a.decision_note,
        }

    async def appeals_for_milestone(self, milestone_id: uuid.UUID) -> list[dict]:
        m = await self._get_milestone(milestone_id)
        if m.review is None:
            return []
        return [self._appeal_out(a) for a in await self.repo.appeals_for_review(m.review.id)]

    async def decide_appeal(
        self, appeal_id: uuid.UUID, status: AppealStatus, note: str | None, user_id
    ) -> dict:
        appeal = await self.repo.get_appeal(appeal_id)
        if appeal is None:
            raise NotFoundError("Appeal not found")
        if appeal.status in (AppealStatus.upheld, AppealStatus.rejected, AppealStatus.withdrawn):
            raise ConflictError("This appeal has already been concluded")
        appeal.status = status
        appeal.decision_note = note
        appeal.decided_by_user_id = user_id
        appeal.decided_at = datetime.now(timezone.utc)
        # An upheld appeal reopens the milestone for a fresh review.
        if status == AppealStatus.upheld:
            review = await self.repo.get_review(appeal.review_id)
            if review is not None:
                milestone = await self.repo.get_milestone(review.milestone_id)
                if milestone is not None:
                    milestone.status = MilestoneStatus.under_review
                review.panel_decision = None
                review.decided_at = None
        await self.session.commit()
        await self.session.refresh(appeal)
        return self._appeal_out(appeal)
