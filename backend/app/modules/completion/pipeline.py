"""Completion pipeline read model — the alumni-handover lens over every completing student.

The three questions a completion coordinator asks:
  * Who can graduate today (classification published, waiting on the ceremony date)?
  * Who is stuck (thesis approved but classification not yet published)?
  * Who just graduated (last 30 days, needs alumni handover)?

Plus a small "award distribution" summary useful for the annual return.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.completion.constants import CompletionStatus
from app.modules.completion.models import Award, Completion
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.models import Student
from app.modules.thesis.constants import ThesisStatus
from app.modules.thesis.models import Thesis


class CompletionPipelineService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def snapshot(
        self,
        *,
        allowed_ids: list[uuid.UUID] | None = None,
        recent_window_days: int = 60,
    ) -> dict:
        today = date.today()
        window_start = today - timedelta(days=recent_window_days)

        # Only students in the completion pipeline: anyone with a Completion record OR a
        # thesis that has reached at least intention_to_submit. Cast a slightly wider net so
        # students on the runway show up too.
        stmt = (
            select(Student, Person, Thesis, Completion)
            .join(Person, Person.id == Student.person_id)
            .outerjoin(Thesis, Thesis.student_id == Student.id)
            .outerjoin(Completion, Completion.student_id == Student.id)
            .where(
                (Completion.id.isnot(None))
                | (Thesis.status.in_([
                    ThesisStatus.intention_to_submit, ThesisStatus.submitted,
                    ThesisStatus.under_examination, ThesisStatus.corrections,
                    ThesisStatus.resubmission, ThesisStatus.approved, ThesisStatus.failed,
                ]))
                | (Student.status == StudentStatus.completed)
            )
        )
        if allowed_ids is not None:
            stmt = stmt.where(Student.id.in_(allowed_ids))
        rows = (await self.session.execute(stmt)).all()

        student_ids = [s.id for s, _, _, _ in rows]

        # Awards keyed by student.
        awards: dict[uuid.UUID, Award] = {}
        if student_ids:
            for a in (await self.session.execute(
                select(Award).where(Award.student_id.in_(student_ids))
            )).scalars().all():
                # keep the latest / most-progressed award per student
                existing = awards.get(a.student_id)
                if existing is None or (a.published_at and not existing.published_at):
                    awards[a.student_id] = a

        by_status: dict[str, int] = {s.value: 0 for s in CompletionStatus}
        by_class_state: dict[str, int] = {k: 0 for k in ("draft", "proposed", "confirmed", "published")}
        by_classification: dict[str, int] = {}

        ready_to_graduate: list[dict] = []
        classification_pending: list[dict] = []
        recently_graduated: list[dict] = []
        certificates_pending = 0

        for student, person, thesis, completion in rows:
            name = f"{person.given_name} {person.family_name}"
            link = f"/students/{student.id}"
            award = awards.get(student.id)

            comp_status = (completion.status.value if completion and hasattr(completion.status, "value")
                           else completion.status if completion else None)
            if comp_status:
                by_status[comp_status] = by_status.get(comp_status, 0) + 1

            if award:
                by_class_state[award.classification_state] = by_class_state.get(award.classification_state, 0) + 1
                if award.classification:
                    by_classification[award.classification] = by_classification.get(award.classification, 0) + 1
                if award.classification_state == "published" and award.certificate_document_id is None:
                    certificates_pending += 1

            # Ready to graduate: award published, completion has no graduation date yet.
            if (award and award.classification_state == "published"
                    and (completion is None or completion.graduation_date is None)):
                ready_to_graduate.append({
                    "studentId": str(student.id),
                    "studentRef": student.student_ref,
                    "personName": name,
                    "classification": award.classification,
                    "publishedAt": award.published_at.isoformat() if award.published_at else None,
                    "hasCertificate": award.certificate_document_id is not None,
                    "link": link,
                })

            # Classification pending: thesis is approved but no published award yet.
            if (thesis is not None and thesis.status == ThesisStatus.approved
                    and (award is None or award.classification_state != "published")):
                classification_pending.append({
                    "studentId": str(student.id),
                    "studentRef": student.student_ref,
                    "personName": name,
                    "classificationState": award.classification_state if award else "draft",
                    "proposedClassification": (award.classification if award else None),
                    "link": link,
                })

            # Recently graduated: completion has a graduation_date within window.
            if completion and completion.graduation_date and completion.graduation_date >= window_start:
                recently_graduated.append({
                    "studentId": str(student.id),
                    "studentRef": student.student_ref,
                    "personName": name,
                    "graduationDate": completion.graduation_date.isoformat(),
                    "classification": (award.classification if award else None),
                    "link": link,
                })

        ready_to_graduate.sort(key=lambda r: (r["publishedAt"] or "", r["personName"]))
        classification_pending.sort(key=lambda r: r["personName"])
        recently_graduated.sort(key=lambda r: r["graduationDate"], reverse=True)

        return {
            "totals": {
                "inPipeline": len(rows),
                "readyToGraduate": len(ready_to_graduate),
                "classificationPending": len(classification_pending),
                "recentlyGraduated": len(recently_graduated),
                "certificatesPending": certificates_pending,
                "recentWindowDays": recent_window_days,
            },
            "byStatus": by_status,
            "byClassificationState": by_class_state,
            "byClassification": [
                {"classification": k, "count": v}
                for k, v in sorted(by_classification.items(), key=lambda kv: -kv[1])
            ],
            "readyToGraduate": ready_to_graduate,
            "classificationPending": classification_pending,
            "recentlyGraduated": recently_graduated,
        }
