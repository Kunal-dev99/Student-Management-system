"""Thesis business rules (arch §8.10)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.person.repository import PersonRepository
from app.modules.person.service import PersonService
from app.modules.student_record.repository import StudentRepository
from app.modules.thesis.constants import (
    CORRECTION_DEADLINE_DAYS,
    OUTCOME_TO_CORRECTION_KIND,
    OUTCOME_TO_THESIS_STATUS,
    ExaminationOutcome,
    ExaminerType,
    ThesisStatus,
    VivaFormat,
)
from app.modules.thesis.models import (
    Examination,
    ExaminerNomination,
    Thesis,
    ThesisCorrection,
)
from app.modules.thesis.repository import ThesisRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ThesisService:
    def __init__(self, repo: ThesisRepository) -> None:
        self.repo = repo
        self.session = repo.session

    async def get_for_student(self, student_id: uuid.UUID, *, allowed_ids=None) -> Thesis | None:
        student = await StudentRepository(self.session).get(student_id, allowed_ids=allowed_ids)
        if student is None:
            raise NotFoundError("Student not found")
        return await self.repo.get_by_student(student_id)

    async def declare_intention(self, student_id: uuid.UUID, title: str | None) -> Thesis:
        if await StudentRepository(self.session).get(student_id) is None:
            raise NotFoundError("Student not found")
        thesis = await self.repo.get_by_student(student_id)
        if thesis is None:
            thesis = Thesis(student_id=student_id)
            self.repo.add(thesis)
        thesis.status = ThesisStatus.intention_to_submit
        thesis.intention_to_submit_at = _now()
        if title:
            thesis.title = title
        await self.session.commit()
        await self.session.refresh(thesis)
        return thesis

    async def _get(self, thesis_id: uuid.UUID) -> Thesis:
        t = await self.repo.get(thesis_id)
        if t is None:
            raise NotFoundError("Thesis not found")
        return t

    async def submit(self, thesis_id: uuid.UUID, title: str | None, document_ref: str | None) -> Thesis:
        thesis = await self._get(thesis_id)
        if thesis.status in (ThesisStatus.approved, ThesisStatus.failed):
            raise WorkflowError(f"Thesis is already {thesis.status.value}")
        thesis.status = ThesisStatus.submitted
        thesis.submitted_at = _now()
        if title:
            thesis.title = title
        if document_ref:
            thesis.document_ref = document_ref

        # Workflow engine: thesis.submitted starts examiner nomination (arch §9.2).
        from app.modules.workflow.engine import WorkflowEngine
        engine = WorkflowEngine(self.session)
        engine.create_task(
            title="Nominate examiners for submitted thesis",
            assignee_role="PGR Administrator",
            aggregate_type="thesis", aggregate_id=thesis.id,
            payload={"studentId": str(thesis.student_id)},
        )
        engine.emit("thesis", thesis.id, "thesis.submitted", {"studentId": str(thesis.student_id)})

        await self.session.commit()
        await self.session.refresh(thesis)
        return thesis

    # --- Examiner management (arch §8.10) ---
    async def nominate_examiner(
        self, thesis_id: uuid.UUID, examiner_person_id: uuid.UUID, examiner_type: ExaminerType,
        *, affiliation: str | None = None, conflict_of_interest: bool = False,
        conflict_note: str | None = None,
    ) -> ExaminerNomination:
        thesis = await self._get(thesis_id)
        if thesis.submitted_at is None:
            raise WorkflowError("Nominate examiners only after the thesis is submitted")
        await PersonService(PersonRepository(self.session)).get_person(examiner_person_id)
        for n in await self.repo.nominations_for_thesis(thesis_id):
            if n.examiner_person_id == examiner_person_id:
                raise ConflictError("That examiner is already nominated for this thesis")
        nomination = ExaminerNomination(
            thesis_id=thesis_id, examiner_person_id=examiner_person_id, examiner_type=examiner_type,
            affiliation=affiliation, conflict_of_interest=conflict_of_interest, conflict_note=conflict_note,
        )
        self.repo.add(nomination)
        await self.session.commit()
        await self.session.refresh(nomination)
        return nomination

    async def approve_nomination(self, nomination_id: uuid.UUID, user_id) -> ExaminerNomination:
        nomination = await self.repo.get_nomination(nomination_id)
        if nomination is None:
            raise NotFoundError("Examiner nomination not found")
        # A declared conflict of interest must be resolved before an examiner can be approved.
        if nomination.conflict_of_interest:
            raise WorkflowError("Cannot approve an examiner with a declared conflict of interest")
        nomination.approved = True
        nomination.approved_by_user_id = user_id
        await self.session.commit()
        await self.session.refresh(nomination)
        return nomination

    async def examiners_for_thesis(self, thesis_id: uuid.UUID) -> list[dict]:
        person_service = PersonService(PersonRepository(self.session))
        out = []
        for n in await self.repo.nominations_for_thesis(thesis_id):
            p = await person_service.get_person(n.examiner_person_id)
            out.append({
                "id": n.id, "examinerPersonId": n.examiner_person_id,
                "examinerName": f"{p.given_name} {p.family_name}",
                "examinerType": n.examiner_type, "approved": n.approved,
                "affiliation": n.affiliation, "conflictOfInterest": n.conflict_of_interest,
                "conflictNote": n.conflict_note,
            })
        return out

    async def schedule_viva(
        self, thesis_id: uuid.UUID, viva_date: date, viva_format: VivaFormat, location: str | None
    ) -> Thesis:
        thesis = await self._get(thesis_id)
        if thesis.submitted_at is None:
            raise WorkflowError("Schedule the viva only after the thesis is submitted")
        # At least one approved examiner should be in place before scheduling.
        noms = await self.repo.nominations_for_thesis(thesis_id)
        if not any(n.approved for n in noms):
            raise WorkflowError("Approve at least one examiner before scheduling the viva")
        if thesis.examination is None:
            thesis.examination = Examination(thesis_id=thesis.id)
        thesis.examination.viva_date = viva_date
        thesis.examination.viva_format = viva_format
        thesis.examination.viva_location = location
        thesis.examination.viva_scheduled_at = _now()
        thesis.status = ThesisStatus.under_examination

        # Notify the student their viva is booked (best-effort, via the notification engine).
        from app.modules.identity.repository import IdentityRepository
        from app.modules.workflow.engine import WorkflowEngine

        student = await StudentRepository(self.session).get(thesis.student_id)
        if student is not None:
            user = await IdentityRepository(self.session).get_user_by_person(student.person_id)
            if user is not None:
                WorkflowEngine(self.session).notify(
                    recipient_user_id=user.id, template="thesis.outcome",
                    payload={"event": "viva_scheduled", "vivaDate": viva_date.isoformat(),
                             "format": viva_format.value, "location": location or "TBC"},
                )
        await self.session.commit()
        await self.session.refresh(thesis)
        return thesis

    async def record_outcome(self, thesis_id: uuid.UUID, outcome: ExaminationOutcome, viva_date: date | None) -> Thesis:
        thesis = await self._get(thesis_id)
        if thesis.submitted_at is None:
            raise WorkflowError("Thesis must be submitted before an examination outcome")
        if thesis.examination is None:
            thesis.examination = Examination(thesis_id=thesis.id)
        thesis.examination.outcome = outcome
        if viva_date is not None:
            thesis.examination.viva_date = viva_date
        thesis.examination.decided_at = _now()
        thesis.status = OUTCOME_TO_THESIS_STATUS[outcome]

        # Open a corrections period when the outcome requires one (minor/major), with a deadline.
        kind = OUTCOME_TO_CORRECTION_KIND.get(outcome)
        if kind is not None:
            base = thesis.examination.viva_date or date.today()
            self.repo.add(ThesisCorrection(
                thesis_id=thesis.id, kind=kind,
                deadline=base + timedelta(days=CORRECTION_DEADLINE_DAYS[kind]),
            ))
        await self.session.commit()
        await self.session.refresh(thesis)
        return thesis

    async def corrections_for_thesis(self, thesis_id: uuid.UUID) -> list[dict]:
        rows = await self.repo.corrections_for_thesis(thesis_id)
        return [
            {
                "id": str(cr.id), "kind": cr.kind.value,
                "deadline": cr.deadline.isoformat() if cr.deadline else None,
                "submittedAt": cr.submitted_at.isoformat() if cr.submitted_at else None,
                "approvedAt": cr.approved_at.isoformat() if cr.approved_at else None,
            }
            for cr in rows
        ]

    async def submit_corrections(self, thesis_id: uuid.UUID) -> dict:
        cr = await self.repo.open_correction(thesis_id)
        if cr is None:
            raise NotFoundError("No open corrections for this thesis")
        cr.submitted_at = _now()
        await self.session.commit()
        return (await self.corrections_for_thesis(thesis_id))[-1]

    async def approve_corrections(self, thesis_id: uuid.UUID, user_id) -> Thesis:
        cr = await self.repo.open_correction(thesis_id)
        if cr is None:
            raise NotFoundError("No open corrections for this thesis")
        if cr.submitted_at is None:
            raise WorkflowError("Corrections have not been submitted yet")
        cr.approved_at = _now()
        cr.approved_by_user_id = user_id
        thesis = await self._get(thesis_id)
        thesis.status = ThesisStatus.approved  # corrections signed off -> thesis approved
        await self.session.commit()
        await self.session.refresh(thesis)
        return thesis
