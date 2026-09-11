"""Thesis-pipeline read model — a lens over every thesis in scope.

Purpose: give the thesis coordinator a single screen answering the three questions they
actually ask every morning:

  * Where is everyone (by stage)?
  * Whose examiner nominations still need approval?
  * Whose viva is coming up, and whose corrections are running out?

Bulk-loaded: one query per table, group in memory. The row-scope is enforced through
`allowed_ids` like every other cohort read.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.person.models import Person
from app.modules.student_record.models import Student
from app.modules.thesis.constants import CORRECTION_DEADLINE_DAYS, CorrectionKind, ThesisStatus
from app.modules.thesis.models import Examination, ExaminerNomination, Thesis, ThesisCorrection


class ThesisPipelineService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def snapshot(
        self,
        *,
        allowed_ids: list[uuid.UUID] | None = None,
        viva_window_days: int = 45,
    ) -> dict:
        today = date.today()

        # Every thesis with the student + person joined once.
        stmt = (
            select(Thesis, Student, Person)
            .join(Student, Student.id == Thesis.student_id)
            .join(Person, Person.id == Student.person_id)
        )
        if allowed_ids is not None:
            stmt = stmt.where(Thesis.student_id.in_(allowed_ids))
        rows = (await self.session.execute(stmt)).all()

        thesis_ids = [t.id for t, _, _ in rows]
        student_of = {t.id: (s, p) for t, s, p in rows}

        # Examinations by thesis id.
        exams: dict[uuid.UUID, Examination] = {}
        if thesis_ids:
            exams = {
                e.thesis_id: e for e in (await self.session.execute(
                    select(Examination).where(Examination.thesis_id.in_(thesis_ids))
                )).scalars().all()
            }

        # Examiner nominations grouped by thesis id — bulk-load with the examiner person's name.
        nominations: dict[uuid.UUID, list[dict]] = {}
        if thesis_ids:
            nom_rows = (await self.session.execute(
                select(
                    ExaminerNomination.id,
                    ExaminerNomination.thesis_id,
                    ExaminerNomination.examiner_type,
                    ExaminerNomination.affiliation,
                    ExaminerNomination.conflict_of_interest,
                    ExaminerNomination.conflict_note,
                    ExaminerNomination.approved,
                    Person.given_name,
                    Person.family_name,
                )
                .join(Person, Person.id == ExaminerNomination.examiner_person_id)
                .where(ExaminerNomination.thesis_id.in_(thesis_ids))
            )).all()
            for nid, tid, etype, aff, coi, coi_note, appr, gn, fn in nom_rows:
                nominations.setdefault(tid, []).append({
                    "id": str(nid),
                    "examinerName": f"{gn} {fn}",
                    "type": etype.value if hasattr(etype, "value") else str(etype),
                    "affiliation": aff,
                    "conflictOfInterest": coi,
                    "conflictNote": coi_note,
                    "approved": appr,
                })

        # Corrections by thesis id.
        corrections: dict[uuid.UUID, list[ThesisCorrection]] = {}
        if thesis_ids:
            for c in (await self.session.execute(
                select(ThesisCorrection).where(ThesisCorrection.thesis_id.in_(thesis_ids))
            )).scalars().all():
                corrections.setdefault(c.thesis_id, []).append(c)

        # --- Aggregation passes ---
        by_status: dict[str, int] = {s.value: 0 for s in ThesisStatus}
        awaiting_approval: list[dict] = []
        upcoming_vivas: list[dict] = []
        corrections_open: list[dict] = []

        window_end = today + timedelta(days=viva_window_days)

        for thesis, student, person in rows:
            status_val = thesis.status.value if hasattr(thesis.status, "value") else str(thesis.status)
            by_status[status_val] = by_status.get(status_val, 0) + 1
            person_name = f"{person.given_name} {person.family_name}"
            student_link = f"/students/{student.id}"

            # Examiner nominations still awaiting approval — surface with CoI info.
            noms = nominations.get(thesis.id, [])
            pending = [n for n in noms if not n["approved"]]
            if pending:
                awaiting_approval.append({
                    "thesisId": str(thesis.id),
                    "studentId": str(student.id),
                    "studentRef": student.student_ref,
                    "personName": person_name,
                    "thesisTitle": thesis.title,
                    "link": student_link,
                    "pendingNominations": pending,
                    "hasConflict": any(n["conflictOfInterest"] for n in pending),
                })

            # Vivas scheduled inside the window.
            ex = exams.get(thesis.id)
            if ex and ex.viva_date and today <= ex.viva_date <= window_end:
                upcoming_vivas.append({
                    "thesisId": str(thesis.id),
                    "studentId": str(student.id),
                    "studentRef": student.student_ref,
                    "personName": person_name,
                    "vivaDate": ex.viva_date.isoformat(),
                    "vivaFormat": ex.viva_format.value if ex.viva_format and hasattr(ex.viva_format, "value") else None,
                    "vivaLocation": ex.viva_location,
                    "daysUntil": (ex.viva_date - today).days,
                    "link": student_link,
                })

            # Corrections open — not yet submitted, deadline present.
            for c in corrections.get(thesis.id, []):
                if c.submitted_at is not None:
                    continue
                deadline = c.deadline
                if deadline is None and ex and ex.viva_date:
                    deadline = ex.viva_date + timedelta(days=CORRECTION_DEADLINE_DAYS[c.kind])
                if deadline is None:
                    continue
                days_left = (deadline - today).days
                kind_val = c.kind.value if hasattr(c.kind, "value") else str(c.kind)
                corrections_open.append({
                    "correctionId": str(c.id),
                    "thesisId": str(thesis.id),
                    "studentId": str(student.id),
                    "studentRef": student.student_ref,
                    "personName": person_name,
                    "kind": kind_val,
                    "deadline": deadline.isoformat(),
                    "daysLeft": days_left,
                    "overdue": days_left < 0,
                    "link": student_link,
                })

        # Deterministic ordering.
        upcoming_vivas.sort(key=lambda v: v["vivaDate"])
        corrections_open.sort(key=lambda c: (c["daysLeft"], c["personName"]))
        awaiting_approval.sort(key=lambda a: (0 if a["hasConflict"] else 1, a["personName"]))

        return {
            "byStatus": by_status,
            "totals": {
                "thesesTotal": len(rows),
                "awaitingExaminerApproval": len(awaiting_approval),
                "upcomingVivas": len(upcoming_vivas),
                "correctionsOpen": len(corrections_open),
                "correctionsOverdue": sum(1 for c in corrections_open if c["overdue"]),
                "vivaWindowDays": viva_window_days,
            },
            "awaitingExaminerApproval": awaiting_approval,
            "upcomingVivas": upcoming_vivas,
            "correctionsOpen": corrections_open,
        }
