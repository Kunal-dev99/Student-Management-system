"""Supervision business rules (arch §8.7). History-preserving assignments."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.person.repository import PersonRepository
from app.modules.person.service import PersonService
from app.modules.student_record.repository import StudentRepository
from app.modules.supervision.constants import (
    MeetingFormat,
    SupervisionStatus,
    SupervisorRole,
)
from app.modules.supervision.models import SupervisionMeeting, SupervisorRelationship
from app.modules.supervision.repository import SupervisionRepository


class SupervisionService:
    def __init__(self, repo: SupervisionRepository) -> None:
        self.repo = repo
        self.session = repo.session

    def _person_service(self) -> PersonService:
        return PersonService(PersonRepository(self.session))

    async def _person_name(self, person_id: uuid.UUID) -> str:
        p = await self._person_service().get_person(person_id)
        return f"{p.given_name} {p.family_name}"

    async def supervisors_for_student(self, student_id: uuid.UUID) -> list[dict]:
        rels = await self.repo.list_for_student(student_id)
        out = []
        for r in rels:
            out.append({
                "id": r.id,
                "supervisorPersonId": r.supervisor_person_id,
                "supervisorName": await self._person_name(r.supervisor_person_id),
                "role": r.role,
                "status": r.status,
                "validFrom": r.valid_from,
                "validTo": r.valid_to,
            })
        return out

    async def assign(
        self, student_id: uuid.UUID, supervisor_person_id: uuid.UUID, role: SupervisorRole,
        *, weighting_pct: int | None = None, max_supervisees: int | None = None,
    ) -> SupervisorRelationship:
        # Phase 8 — the capacity limit is an institution setting; the shipped constant is only
        # the default. Passing max_supervisees explicitly (tests) still wins.
        if max_supervisees is None:
            from app.modules.settings.service import setting_value

            max_supervisees = await setting_value(self.session, "supervision.max_supervisees")
        # Both the student and the supervising person must exist (service boundary).
        student = await StudentRepository(self.session).get(student_id)
        if student is None:
            raise NotFoundError("Student not found")
        await self._person_service().get_person(supervisor_person_id)

        # No duplicate active relationship for the same supervisor on the same student.
        for r in await self.repo.list_for_student(student_id):
            if r.supervisor_person_id == supervisor_person_id and r.valid_to is None:
                raise ConflictError("This supervisor is already active for the student")

        # Phase 4B.5 — capacity guard: a supervisor may not exceed their supervisee limit.
        current = await self.repo.count_active_for_supervisor(supervisor_person_id)
        if current >= max_supervisees:
            raise WorkflowError(
                f"Supervisor is at capacity ({current}/{max_supervisees} current supervisees)"
            )
        if weighting_pct is not None and not (0 < weighting_pct <= 100):
            raise WorkflowError("weightingPct must be between 1 and 100")

        rel = SupervisorRelationship(
            student_id=student_id, supervisor_person_id=supervisor_person_id,
            role=role, status=SupervisionStatus.active, valid_from=date.today(), valid_to=None,
            weighting_pct=weighting_pct,
        )
        self.repo.add(rel)
        await self.session.commit()
        await self.session.refresh(rel)
        return rel

    async def end(self, rel_id: uuid.UUID, reason: str | None = None) -> SupervisorRelationship:
        rel = await self.repo.get(rel_id)
        if rel is None:
            raise NotFoundError("Supervisor relationship not found")
        if rel.valid_to is None:
            rel.valid_to = date.today()
            rel.status = SupervisionStatus.ended
            rel.end_reason = reason
            await self.session.commit()
            await self.session.refresh(rel)
        return rel

    async def capacity_for(self, person_id: uuid.UUID, max_supervisees: int | None = None) -> dict:
        if max_supervisees is None:
            from app.modules.settings.service import setting_value

            max_supervisees = await setting_value(self.session, "supervision.max_supervisees")
        current = await self.repo.count_active_for_supervisor(person_id)
        return {
            "supervisorPersonId": str(person_id),
            "current": current,
            "max": max_supervisees,
            "atCapacity": current >= max_supervisees,
        }

    # --- Phase 4B.5 — supervision meeting log (arch §8.7) ---

    def _meeting_out(self, m: SupervisionMeeting, supervisor_name: str | None = None) -> dict:
        return {
            "id": str(m.id),
            "studentId": str(m.student_id),
            "supervisorPersonId": str(m.supervisor_person_id) if m.supervisor_person_id else None,
            "supervisorName": supervisor_name,
            "metOn": m.met_on.isoformat(),
            "format": m.format.value if hasattr(m.format, "value") else m.format,
            "durationMinutes": m.duration_minutes,
            "notes": m.notes,
            "actions": m.actions,
            "nextMeetingOn": m.next_meeting_on.isoformat() if m.next_meeting_on else None,
            "studentConfirmed": m.student_confirmed,
        }

    async def meetings_for_student(self, student_id: uuid.UUID) -> list[dict]:
        out = []
        for m in await self.repo.meetings_for_student(student_id):
            name = await self._person_name(m.supervisor_person_id) if m.supervisor_person_id else None
            out.append(self._meeting_out(m, name))
        return out

    async def record_meeting(
        self, student_id: uuid.UUID, *, supervisor_person_id: uuid.UUID | None, met_on: date,
        format: MeetingFormat, duration_minutes: int | None, notes: str | None,
        actions: str | None, next_meeting_on: date | None, recorded_by_user_id: uuid.UUID | None,
    ) -> dict:
        if await StudentRepository(self.session).get(student_id) is None:
            raise NotFoundError("Student not found")
        if met_on > date.today():
            raise WorkflowError("A supervision meeting cannot be recorded in the future")
        if supervisor_person_id is not None:
            await self._person_service().get_person(supervisor_person_id)
        meeting = SupervisionMeeting(
            student_id=student_id, supervisor_person_id=supervisor_person_id, met_on=met_on,
            format=format, duration_minutes=duration_minutes, notes=notes, actions=actions,
            next_meeting_on=next_meeting_on, recorded_by_user_id=recorded_by_user_id,
        )
        self.repo.add(meeting)
        await self.session.commit()
        await self.session.refresh(meeting)
        name = await self._person_name(supervisor_person_id) if supervisor_person_id else None
        return self._meeting_out(meeting, name)

    async def confirm_meeting(self, meeting_id: uuid.UUID) -> dict:
        m = await self.repo.get_meeting(meeting_id)
        if m is None:
            raise NotFoundError("Supervision meeting not found")
        m.student_confirmed = True
        m.student_confirmed_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(m)
        name = await self._person_name(m.supervisor_person_id) if m.supervisor_person_id else None
        return self._meeting_out(m, name)

    async def meeting_compliance(self, student_id: uuid.UUID) -> dict:
        """Is this student's supervision record up to date (arch §8.7 evidencing)?"""
        from app.modules.settings.service import setting_value

        interval = await setting_value(self.session, "supervision.expected_meeting_interval_days")
        last = await self.repo.last_meeting_for_student(student_id)
        if last is None:
            return {"lastMeetingOn": None, "daysSince": None, "overdue": True,
                    "expectedIntervalDays": interval}
        days = (date.today() - last.met_on).days
        return {
            "lastMeetingOn": last.met_on.isoformat(),
            "daysSince": days,
            "overdue": days > interval,
            "expectedIntervalDays": interval,
        }

    async def caseload(self, person_id: uuid.UUID) -> list[dict]:
        rels = await self.repo.active_for_supervisor(person_id)
        student_repo = StudentRepository(self.session)
        out = []
        for r in rels:
            student = await student_repo.get(r.student_id)
            if student is None:
                continue
            compliance = await self.meeting_compliance(student.id)
            out.append({
                "relationshipId": r.id,
                "studentId": student.id,
                "studentRef": student.student_ref,
                "personName": await self._person_name(student.person_id),
                "role": r.role,
                # Phase 4B.5 — surface supervision-record health right on the caseload.
                "lastMeetingOn": compliance["lastMeetingOn"],
                "meetingOverdue": compliance["overdue"],
            })
        return out

    async def supervised_student_ids(self, person_id: uuid.UUID) -> list[uuid.UUID]:
        """For row-scoping: the students this supervisor may currently see (arch §12.3)."""
        return await self.repo.active_student_ids_for_supervisor(person_id)
