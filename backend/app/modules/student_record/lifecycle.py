"""PGR exception lifecycle (Phase 6.5 — CIO vision GAP-06).

Suspensions, extensions and mode changes materially change a research timeline. The rules here are
deliberately **deterministic and explainable**: every adjustment records the arithmetic that
produced it, and the original agreed end date is never overwritten.

    expected_end_date = original_expected_end_date + Σ(days_applied of approved events)

Approval is required (user decision, 2026-08-22): requesting an event raises a task and changes
nothing; only approval moves dates, and both requester and approver are recorded.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone
from app.modules.student_record.constants import (
    PART_TIME_FACTOR,
    SUSPENDABLE_STATUSES,
    LifecycleEventStatus,
    LifecycleEventType,
    StudentStatus,
    StudyMode,
)
from app.modules.student_record.models import Student, StudentLifecycleEvent


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LifecycleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------------- helpers ----------------

    async def _get_student(self, student_id: uuid.UUID) -> Student:
        st = (await self.session.execute(
            select(Student).where(Student.id == student_id)
        )).scalars().unique().one_or_none()
        if st is None:
            raise NotFoundError("Student not found")
        return st

    async def _get_event(self, event_id: uuid.UUID) -> StudentLifecycleEvent:
        ev = (await self.session.execute(
            select(StudentLifecycleEvent).where(StudentLifecycleEvent.id == event_id)
        )).scalar_one_or_none()
        if ev is None:
            raise NotFoundError("Lifecycle event not found")
        return ev

    async def events_for_student(self, student_id: uuid.UUID) -> list[StudentLifecycleEvent]:
        rows = await self.session.execute(
            select(StudentLifecycleEvent)
            .where(StudentLifecycleEvent.student_id == student_id)
            .order_by(StudentLifecycleEvent.start_date)
        )
        return list(rows.scalars().all())

    @staticmethod
    def out(ev: StudentLifecycleEvent) -> dict:
        return {
            "id": str(ev.id),
            "studentId": str(ev.student_id),
            "eventType": ev.event_type.value if hasattr(ev.event_type, "value") else ev.event_type,
            "status": ev.status.value if hasattr(ev.status, "value") else ev.status,
            "startDate": ev.start_date.isoformat(),
            "endDate": ev.end_date.isoformat() if ev.end_date else None,
            "actualEndDate": ev.actual_end_date.isoformat() if ev.actual_end_date else None,
            "extensionDays": ev.extension_days,
            "previousMode": ev.previous_mode.value if ev.previous_mode else None,
            "newMode": ev.new_mode.value if ev.new_mode else None,
            "reason": ev.reason,
            "daysApplied": ev.days_applied,
            "decisionNote": ev.decision_note,
            "decidedAt": ev.decided_at.isoformat() if ev.decided_at else None,
        }

    # ---------------- request ----------------

    async def request_event(
        self,
        student_id: uuid.UUID,
        *,
        event_type: LifecycleEventType,
        reason: str,
        start_date: date,
        end_date: date | None = None,
        extension_days: int | None = None,
        new_mode: StudyMode | None = None,
        requested_by_user_id: uuid.UUID | None = None,
    ) -> StudentLifecycleEvent:
        """Record a request. Changes nothing about the student until it is approved."""
        student = await self._get_student(student_id)
        if not (reason or "").strip():
            raise WorkflowError("A reason is required")

        if event_type is LifecycleEventType.suspension:
            if student.status not in SUSPENDABLE_STATUSES:
                raise WorkflowError(
                    f"A student with status '{student.status.value}' cannot be suspended"
                )
            if end_date is None:
                raise WorkflowError("A suspension needs a planned end date")
            if end_date <= start_date:
                raise WorkflowError("The suspension end date must be after the start date")
            await self._assert_no_overlap(student_id, start_date, end_date)
        elif event_type is LifecycleEventType.extension:
            if not extension_days or extension_days <= 0:
                raise WorkflowError("An extension needs a positive number of days")
        elif event_type is LifecycleEventType.mode_change:
            if new_mode is None:
                raise WorkflowError("A mode change needs the new study mode")
            if new_mode == student.study_mode:
                raise WorkflowError("The student is already studying in that mode")

        event = StudentLifecycleEvent(
            student_id=student_id, event_type=event_type,
            status=LifecycleEventStatus.requested,
            start_date=start_date, end_date=end_date, extension_days=extension_days,
            previous_mode=student.study_mode if event_type is LifecycleEventType.mode_change else None,
            new_mode=new_mode, reason=reason, requested_by_user_id=requested_by_user_id,
        )
        self.session.add(event)
        await self.session.flush()

        # Approval is a human decision — raise it as work, not a silent change (arch §9.2).
        from app.modules.workflow.engine import WorkflowEngine

        WorkflowEngine(self.session).create_task(
            title=f"Approve {event_type.value.replace('_', ' ')} request",
            assignee_role="PGR Administrator",
            aggregate_type="student_lifecycle_event", aggregate_id=event.id,
            payload={"studentId": str(student_id), "eventType": event_type.value,
                     "startDate": start_date.isoformat()},
        )
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def _assert_no_overlap(self, student_id: uuid.UUID, start: date, end: date) -> None:
        for ev in await self.events_for_student(student_id):
            if ev.event_type is not LifecycleEventType.suspension:
                continue
            if ev.status not in (LifecycleEventStatus.requested, LifecycleEventStatus.approved):
                continue
            other_end = ev.actual_end_date or ev.end_date or ev.start_date
            if start <= other_end and ev.start_date <= end:
                raise ConflictError(
                    f"Overlaps an existing suspension ({ev.start_date} to {other_end})"
                )

    # ---------------- decide ----------------

    async def approve_event(
        self, event_id: uuid.UUID, *, approver_user_id: uuid.UUID | None, note: str | None = None
    ) -> dict:
        event = await self._get_event(event_id)
        if event.status is not LifecycleEventStatus.requested:
            raise ConflictError(f"This request is already {event.status.value}")
        student = await self._get_student(event.student_id)

        event.status = LifecycleEventStatus.approved
        event.approved_by_user_id = approver_user_id
        event.decided_at = _now()
        event.decision_note = note

        if event.event_type is LifecycleEventType.suspension:
            # Days are provisional until the student actually returns; the planned window is
            # applied now and corrected on return.
            event.days_applied = (event.end_date - event.start_date).days
            student.status = StudentStatus.suspended
        elif event.event_type is LifecycleEventType.extension:
            event.days_applied = event.extension_days
        elif event.event_type is LifecycleEventType.mode_change:
            from app.modules.settings.service import setting_value

            factor = await setting_value(self.session, "lifecycle.part_time_factor")
            event.days_applied = self._mode_change_days(student, event, factor)
            student.study_mode = event.new_mode

        recalc = await self._recalculate(student)
        await self.session.commit()
        await self.session.refresh(event)
        return {"event": self.out(event), "recalculation": recalc}

    async def reject_event(
        self, event_id: uuid.UUID, *, approver_user_id: uuid.UUID | None, note: str | None = None
    ) -> dict:
        event = await self._get_event(event_id)
        if event.status is not LifecycleEventStatus.requested:
            raise ConflictError(f"This request is already {event.status.value}")
        event.status = LifecycleEventStatus.rejected
        event.approved_by_user_id = approver_user_id
        event.decided_at = _now()
        event.decision_note = note
        await self.session.commit()
        await self.session.refresh(event)
        return {"event": self.out(event), "recalculation": None}

    @staticmethod
    def _mode_change_days(
        student: Student, event: StudentLifecycleEvent, factor: float = PART_TIME_FACTOR
    ) -> int:
        """Moving to part-time stretches the remaining time; moving to full-time compresses it.

        Phase 8: `factor` comes from the "lifecycle.part_time_factor" institution setting at the
        moment of approval; already-approved events keep the days that were applied then.
        """
        if not student.expected_end_date or event.start_date >= student.expected_end_date:
            return 0
        remaining = (student.expected_end_date - event.start_date).days
        if event.new_mode is StudyMode.part_time:
            return int(remaining * (factor - 1))
        return -int(remaining * (1 - 1 / factor))

    # ---------------- return from suspension ----------------

    async def record_return(
        self, student_id: uuid.UUID, *, returned_on: date | None = None
    ) -> dict:
        """End the current suspension. If the student returned early or late, the difference is
        applied so the expected end date reflects what actually happened."""
        student = await self._get_student(student_id)
        if student.status not in (StudentStatus.suspended, StudentStatus.on_leave):
            raise WorkflowError("This student is not currently suspended")
        current = await self._current_suspension(student_id)
        if current is None:
            raise NotFoundError("No approved suspension to return from")

        actual = returned_on or date.today()
        if actual < current.start_date:
            raise WorkflowError("The return date cannot precede the suspension start")
        current.actual_end_date = actual
        current.days_applied = (actual - current.start_date).days   # correct the provisional figure
        student.status = StudentStatus.active

        recalc = await self._recalculate(student)
        await self.session.commit()
        return {"event": self.out(current), "recalculation": recalc}

    async def _current_suspension(self, student_id: uuid.UUID) -> StudentLifecycleEvent | None:
        for ev in sorted(await self.events_for_student(student_id), key=lambda e: e.start_date, reverse=True):
            if (ev.event_type is LifecycleEventType.suspension
                    and ev.status is LifecycleEventStatus.approved
                    and ev.actual_end_date is None):
                return ev
        return None

    # ---------------- recalculation ----------------

    async def _recalculate(self, student: Student) -> dict:
        """Rebuild the expected end date from the original plus every approved adjustment.

        Recomputing from the baseline (rather than incrementally nudging) means the result is the
        same however many times it runs, and a rejected or corrected event cannot leave residue.
        Only *undecided* milestones move — a decided milestone is a historical fact.
        """
        if student.original_expected_end_date is None:
            # First adjustment: capture the agreed baseline before changing anything.
            student.original_expected_end_date = student.expected_end_date

        events = await self.events_for_student(student.id)
        approved = [e for e in events if e.status is LifecycleEventStatus.approved]
        total_days = sum(e.days_applied or 0 for e in approved)

        breakdown = [
            {"eventType": e.event_type.value, "days": e.days_applied or 0,
             "from": e.start_date.isoformat()}
            for e in approved if (e.days_applied or 0) != 0
        ]

        if student.original_expected_end_date is None:
            # No expected end was ever agreed — nothing to shift, but report honestly.
            return {
                "originalExpectedEnd": None, "newExpectedEnd": None,
                "totalDaysApplied": total_days, "breakdown": breakdown,
                "milestonesShifted": 0,
                "note": "No expected end date is set for this student, so no dates were shifted.",
            }

        from datetime import timedelta

        previous = student.expected_end_date
        student.expected_end_date = student.original_expected_end_date + timedelta(days=total_days)
        shift = (student.expected_end_date - previous).days if previous else 0

        shifted = 0
        if shift:
            rows = await self.session.execute(
                select(Milestone).where(
                    Milestone.student_id == student.id,
                    Milestone.status != MilestoneStatus.decided,   # decided = historical fact
                    Milestone.due_date.is_not(None),
                )
            )
            for m in rows.scalars().unique().all():
                m.due_date = m.due_date + timedelta(days=shift)
                shifted += 1

        return {
            "originalExpectedEnd": student.original_expected_end_date.isoformat(),
            "newExpectedEnd": student.expected_end_date.isoformat(),
            "totalDaysApplied": total_days,
            "breakdown": breakdown,
            "milestonesShifted": shifted,
            "note": f"Expected end moved {total_days} day(s) from the agreed baseline; "
                    f"{shifted} undecided milestone(s) shifted by {shift} day(s).",
        }

    # ---------------- worker support ----------------

    async def auto_return_due(self) -> int:
        """Return students whose approved suspension has reached its planned end date."""
        today = date.today()
        rows = await self.session.execute(
            select(StudentLifecycleEvent).where(
                StudentLifecycleEvent.event_type == LifecycleEventType.suspension,
                StudentLifecycleEvent.status == LifecycleEventStatus.approved,
                StudentLifecycleEvent.actual_end_date.is_(None),
                StudentLifecycleEvent.end_date.is_not(None),
                StudentLifecycleEvent.end_date <= today,
            )
        )
        returned = 0
        for ev in rows.scalars().all():
            student = await self._get_student(ev.student_id)
            if student.status not in (StudentStatus.suspended, StudentStatus.on_leave):
                continue
            ev.actual_end_date = ev.end_date
            ev.days_applied = (ev.end_date - ev.start_date).days
            student.status = StudentStatus.active
            await self._recalculate(student)
            returned += 1
        if returned:
            await self.session.commit()
        return returned
