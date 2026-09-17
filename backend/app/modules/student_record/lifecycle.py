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
    DEFAULT_PART_TIME_INTENSITY_PCT,
    FULL_TIME_INTENSITY_PCT,
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
            "previousIntensityPct": ev.previous_intensity_pct,
            "intensityPct": ev.intensity_pct,
            "reason": ev.reason,
            "leaveCategory": ev.leave_category,
            "daysApplied": ev.days_applied,
            "decisionNote": ev.decision_note,
            "decidedAt": ev.decided_at.isoformat() if ev.decided_at else None,
            "previousProgrammeId": str(ev.previous_programme_id) if ev.previous_programme_id else None,
            "newProgrammeId": str(ev.new_programme_id) if ev.new_programme_id else None,
            "effectiveDate": ev.effective_date.isoformat() if ev.effective_date else None,
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
        intensity_pct: int | None = None,
        new_programme_id: uuid.UUID | None = None,
        leave_category: str | None = None,
        requested_by_user_id: uuid.UUID | None = None,
    ) -> StudentLifecycleEvent:
        """Record a request. Changes nothing about the student until it is approved."""
        student = await self._get_student(student_id)
        if not (reason or "").strip():
            raise WorkflowError("A reason is required")

        previous_intensity: int | None = None
        previous_programme_id: uuid.UUID | None = None

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
        elif event_type is LifecycleEventType.intensity_change:
            if intensity_pct is None or not (1 <= intensity_pct <= 100):
                raise WorkflowError("An intensity change needs a percentage between 1 and 100")
            previous_intensity = await self._current_intensity(student)
            if intensity_pct == previous_intensity:
                raise WorkflowError(f"The student is already studying at {intensity_pct}% intensity")
        elif event_type is LifecycleEventType.programme_change:
            if new_programme_id is None:
                raise WorkflowError("A programme change needs the new programme id")
            if student.programme_id == new_programme_id:
                raise WorkflowError("The student is already on that programme")
            from app.modules.student_record.models import Programme
            new_prog = await self.session.get(Programme, new_programme_id)
            if new_prog is None:
                raise NotFoundError("Target programme not found")
            previous_programme_id = student.programme_id

        event = StudentLifecycleEvent(
            student_id=student_id, event_type=event_type,
            status=LifecycleEventStatus.requested,
            start_date=start_date, end_date=end_date, extension_days=extension_days,
            previous_mode=student.study_mode if event_type is LifecycleEventType.mode_change else None,
            new_mode=new_mode,
            previous_intensity_pct=previous_intensity,
            intensity_pct=intensity_pct if event_type is LifecycleEventType.intensity_change else None,
            previous_programme_id=previous_programme_id,
            new_programme_id=(
                new_programme_id if event_type is LifecycleEventType.programme_change else None
            ),
            effective_date=(
                start_date if event_type is LifecycleEventType.programme_change else None
            ),
            # leave_category is only meaningful for a suspension — silently drop it on other types
            # so a stray field on the request doesn't mislabel a mode change as "medical".
            leave_category=(
                leave_category if event_type is LifecycleEventType.suspension else None
            ),
            reason=reason, requested_by_user_id=requested_by_user_id,
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

    async def request_programme_change(
        self,
        student_id: uuid.UUID,
        *,
        new_programme_id: uuid.UUID,
        effective_date: date,
        reason: str,
        requested_by_user_id: uuid.UUID | None = None,
    ) -> StudentLifecycleEvent:
        """Convenience wrapper — mid-term programme transfer piggy-backs on ``request_event`` so
        the same requested -> approve -> recalculate pipeline runs for it. ``effective_date`` is
        stored on both ``start_date`` (for the shared event surface) and ``effective_date`` (the
        programme-change-specific field the recalculate step reads)."""
        return await self.request_event(
            student_id,
            event_type=LifecycleEventType.programme_change,
            reason=reason,
            start_date=effective_date,
            new_programme_id=new_programme_id,
            requested_by_user_id=requested_by_user_id,
        )

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
        elif event.event_type is LifecycleEventType.intensity_change:
            prev = event.previous_intensity_pct or await self._current_intensity(student)
            event.previous_intensity_pct = prev
            event.days_applied = self._intensity_change_days(
                student, event.start_date, prev, event.intensity_pct or prev
            )
            # Study mode stays a derived summary of the intensity.
            student.study_mode = (
                StudyMode.full_time if (event.intensity_pct or 0) >= FULL_TIME_INTENSITY_PCT
                else StudyMode.part_time
            )
        elif event.event_type is LifecycleEventType.programme_change:
            # Programme transfer has its own recalc — no days_applied contribution; the
            # timeline is rebuilt from the new programme's duration, not from a delta.
            recalc = await self._recalculate_programme_change(student, event)
            await self.session.commit()
            await self.session.refresh(event)
            return {"event": self.out(event), "recalculation": recalc,
                    "warnings": recalc.get("warnings", []),
                    "crossType": recalc.get("crossType", False)}

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

    # ---------------- study intensity (ICR G4) ----------------

    @staticmethod
    def _intensity_change_days(student: Student, start: date, prev_pct: int, new_pct: int) -> int:
        """Rescale the remaining time by the REAL ratio of the old to new intensity.

        The remaining work is fixed; doing it at ``new_pct`` instead of ``prev_pct`` takes
        prev/new as long. Slowing down (new < prev) lengthens the journey, speeding up shortens
        it. This replaces the fixed part-time-factor step with the actual percentages.
        """
        if not student.expected_end_date or start >= student.expected_end_date or not new_pct:
            return 0
        remaining = (student.expected_end_date - start).days
        return int(round(remaining * (prev_pct / new_pct - 1)))

    async def _intensity_events(self, student_id: uuid.UUID) -> list[StudentLifecycleEvent]:
        return sorted(
            [e for e in await self.events_for_student(student_id)
             if e.event_type is LifecycleEventType.intensity_change
             and e.status is LifecycleEventStatus.approved and e.intensity_pct],
            key=lambda e: e.start_date,
        )

    async def _current_intensity(self, student: Student) -> int:
        """The student's FTE % **as of today**: the most recent approved change whose effective
        date has arrived. A change dated in the future is scheduled, not current — so it does not
        move "now". Falls back to the study-mode default when nothing has taken effect yet."""
        today = date.today()
        events = await self._intensity_events(student.id)
        effective = [e for e in events if e.start_date <= today]
        if effective:
            return effective[-1].intensity_pct  # type: ignore[return-value]
        if events:
            # Changes exist but all take effect in the future — "now" is the pre-change baseline
            # (the first change's recorded previous %), not a flipped study_mode.
            return events[0].previous_intensity_pct or (
                FULL_TIME_INTENSITY_PCT if student.study_mode is StudyMode.full_time
                else DEFAULT_PART_TIME_INTENSITY_PCT)
        return (FULL_TIME_INTENSITY_PCT if student.study_mode is StudyMode.full_time
                else DEFAULT_PART_TIME_INTENSITY_PCT)

    async def intensity_impact_preview(
        self, student: Student, *, prev_pct: int, new_pct: int, effective: date,
    ) -> dict:
        """What approving an intensity change WOULD do — deterministic, computed from the same
        arithmetic approval uses (ICR G6/G4). Lets the admin see the consequence before deciding."""
        days_delta = self._intensity_change_days(student, effective, prev_pct, new_pct)
        base = {
            "previousPct": prev_pct, "newPct": new_pct, "daysDelta": days_delta,
            "startDate": student.start_date.isoformat() if student.start_date else None,
            "currentEnd": student.expected_end_date.isoformat() if student.expected_end_date else None,
        }
        if student.expected_end_date is None:
            return {
                **base, "projectedEnd": None, "milestonesAffected": 0, "milestones": [],
                "summary": (
                    f"Sets study intensity to {new_pct}%. No expected end date is set for this "
                    "student, so the timeline will not move — set a programme duration or end date "
                    "first if this change should extend it."
                ),
            }
        from datetime import timedelta

        from app.modules.progression.models import Milestone, MilestoneDefinition

        projected_end = student.expected_end_date + timedelta(days=days_delta)

        # The specific milestones that would move (undecided, dated) with their current -> projected
        # due dates — so the approver sees exactly what shifts, not just a count.
        rows = (await self.session.execute(
            select(Milestone).where(
                Milestone.student_id == student.id,
                Milestone.status != MilestoneStatus.decided,
                Milestone.due_date.is_not(None),
            )
        )).scalars().unique().all()
        def_ids = {m.milestone_definition_id for m in rows if m.milestone_definition_id}
        names: dict = {}
        if def_ids:
            for d in (await self.session.execute(
                select(MilestoneDefinition).where(MilestoneDefinition.id.in_(def_ids))
            )).scalars().all():
                names[d.id] = d.name
        milestones = sorted(
            [
                {
                    "name": m.name or names.get(m.milestone_definition_id) or "Milestone",
                    "currentDue": m.due_date.isoformat(),
                    "projectedDue": (m.due_date + timedelta(days=days_delta)).isoformat(),
                }
                for m in rows
            ],
            key=lambda x: x["currentDue"],
        )
        affected = len(milestones) if days_delta else 0

        direction = "extend" if days_delta > 0 else ("shorten" if days_delta < 0 else "keep")
        summary = (
            f"Sets study intensity to {new_pct}% (from {prev_pct}%). "
            + (f"Would {direction} the expected end by {abs(days_delta)} day(s) to "
               f"{projected_end.isoformat()}"
               + (f", shifting {affected} undecided milestone(s)." if affected else ".")
               if days_delta else "The expected end does not change.")
        )
        return {
            **base,
            "projectedEnd": projected_end.isoformat(),
            "milestonesAffected": affected,
            "milestones": milestones if days_delta else [],
            "summary": summary,
        }

    async def intensity_impact_narrated(self, event_id: uuid.UUID) -> dict:
        """The deterministic impact plus an AI-worded paragraph over the SAME figures (ICR G6).

        The narration is grounded — the model may only quote the figures we computed — and falls
        back to the deterministic summary when the model is off. Called on demand (when the
        approver opens the decision), never in a list, so it costs one call only when needed.
        """
        event = await self._get_event(event_id)
        if event.event_type is not LifecycleEventType.intensity_change or not event.intensity_pct:
            raise WorkflowError("Impact narration is only available for an intensity change")
        student = await self._get_student(event.student_id)
        prev = event.previous_intensity_pct or await self._current_intensity(student)
        impact = await self.intensity_impact_preview(
            student, prev_pct=prev, new_pct=event.intensity_pct, effective=event.start_date,
        )

        from app.ai.narrate import narrate as ai_narrate
        from app.ai.types import Evidence
        from app.modules.person.models import Person

        person = await self.session.get(Person, student.person_id)
        first_name = person.given_name if person else "the student"

        figures = {
            "new intensity": f"{event.intensity_pct}%",
            "previous intensity": f"{prev}%",
            "day change": str(impact["daysDelta"]),
            "milestones affected": str(impact["milestonesAffected"]),
        }
        if impact["projectedEnd"]:
            figures["projected end date"] = impact["projectedEnd"]

        narration = await ai_narrate(
            evidence=Evidence(figures=figures, context={"studentFirstName": first_name}),
            question=(
                f"Explain to the administrator, in one or two short sentences, what APPROVING this "
                f"study-intensity change will do for {first_name}. State the new intensity, whether "
                "the expected end date moves and to when, and that undecided milestones shift with "
                "it. If the day change is 0, say the timeline does not move and why (no end date "
                "set). Neutral, factual; only use the figures given; no metaphors."
            ),
            fallback_template=impact["summary"],
        )
        return {
            **impact,
            "narration": narration.body,
            "narrationSource": narration.provenance.source,   # "model" or "fallback"
            "model": narration.provenance.model,
        }

    async def intensity_periods(self, student: Student) -> list[dict]:
        """The dated FTE-% timeline, derived from approved intensity changes + registration."""
        start = student.start_date or date.today()
        end_cap = student.expected_end_date or date.today()
        events = await self._intensity_events(student.id)
        base = (events[0].previous_intensity_pct if events and events[0].previous_intensity_pct
                else (FULL_TIME_INTENSITY_PCT if student.study_mode is StudyMode.full_time
                      else DEFAULT_PART_TIME_INTENSITY_PCT))
        periods: list[dict] = []
        cur_from, cur_pct = start, base
        for e in events:
            if e.start_date > cur_from:
                periods.append({"from": cur_from, "to": e.start_date, "pct": cur_pct})
            cur_from, cur_pct = e.start_date, e.intensity_pct
        periods.append({"from": cur_from, "to": max(end_cap, cur_from), "pct": cur_pct})
        return periods

    async def fte_for_year(self, student: Student, *, year: int, start_month: int = 8) -> float | None:
        """Time-weighted average FTE % over the academic year starting ``start_month`` of ``year``.
        Maps to HESA STULOAD. Returns None when the student was not registered in that window."""
        win_start = date(year, start_month, 1)
        win_end = date(year + 1, start_month, 1)
        total_days = 0
        weighted = 0.0
        for p in await self.intensity_periods(student):
            lo = max(p["from"], win_start)
            hi = min(p["to"], win_end)
            days = (hi - lo).days
            if days > 0:
                total_days += days
                weighted += days * p["pct"]
        if total_days == 0:
            return None
        return round(weighted / total_days, 1)

    async def intensity_overview(self, student_id: uuid.UUID) -> dict:
        student = await self._get_student(student_id)
        periods = await self.intensity_periods(student)
        return {
            "studentId": str(student_id),
            "currentPct": await self._current_intensity(student),
            "periods": [
                {"from": p["from"].isoformat(), "to": p["to"].isoformat(), "pct": p["pct"]}
                for p in periods
            ],
        }

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

    async def _recalculate_programme_change(
        self, student: Student, event: StudentLifecycleEvent,
    ) -> dict:
        """Swap the student's current programme, rebuild the milestone schedule from the new
        programme's definitions, and recompute the expected end date from the effective date +
        the new programme's duration. The original agreed end date stays put (baseline immutability
        — the transfer changes the plan going forward, it does not rewrite what was agreed at
        registration).

        Cross-type transfers (research <-> taught) are allowed — the domain model won't stop you —
        but a warning is returned so the approver sees the carry-over concerns.
        """
        from datetime import timedelta

        from app.modules.progression.models import Milestone, MilestoneDefinition
        from app.modules.student_record.models import Programme
        from app.modules.student_record.service import _add_months

        old_prog = await self.session.get(Programme, student.programme_id) if student.programme_id else None
        new_prog = await self.session.get(Programme, event.new_programme_id)
        if new_prog is None:
            raise NotFoundError("Target programme not found")

        effective = event.effective_date or event.start_date
        cross_type = bool(old_prog and old_prog.programme_type != new_prog.programme_type)
        warnings: list[str] = []
        if cross_type:
            warnings.append(
                f"Cross-type transfer: {old_prog.programme_type.value} -> {new_prog.programme_type.value}. "
                "Existing supervisors and funding arrangements are student-scoped and carry over unchanged; "
                "review whether the supervisory team and funding source remain appropriate for the new programme."
            )
        else:
            warnings.append(
                "Existing supervisors and funding arrangements carry over unchanged — review whether they "
                "remain appropriate under the new programme."
            )

        # 1) Swap the current programme pointer.
        student.programme_id = new_prog.id

        # 2) Cancel undecided milestones from the old schedule (decided = historical fact).
        cancelled = 0
        cancel_note = f"superseded by programme change to {new_prog.code}"
        rows = (await self.session.execute(
            select(Milestone).where(Milestone.student_id == student.id)
        )).scalars().unique().all()
        for m in rows:
            if m.status == MilestoneStatus.decided or m.status == MilestoneStatus.cancelled:
                continue
            m.status = MilestoneStatus.cancelled
            # Preserve the reason inline (Milestone has no dedicated note column) — the existing
            # name (or definition-derived name) is kept intact by prefixing.
            if m.name:
                m.name = f"{m.name} ({cancel_note})"
            else:
                m.name = cancel_note
            cancelled += 1

        # 3) Generate the new programme's milestone schedule from the effective date. We inline the
        #    generator here (rather than calling ProgressionService.generate_full_schedule) because
        #    the offsets must anchor on ``effective``, not on the student's original start_date.
        defs = (await self.session.execute(
            select(MilestoneDefinition)
            .where(MilestoneDefinition.programme_id == new_prog.id)
            .order_by(MilestoneDefinition.due_offset_days)
        )).scalars().all()
        from app.modules.progression.constants import MilestoneOrigin
        generated = 0
        today = date.today()
        for defn in defs:
            due = effective + timedelta(days=defn.due_offset_days)
            status = MilestoneStatus.due if due <= today else MilestoneStatus.not_started
            self.session.add(Milestone(
                student_id=student.id,
                milestone_definition_id=defn.id,
                due_date=due,
                status=status,
                origin=MilestoneOrigin.template,
            ))
            generated += 1

        # 4) Recompute expected end from the effective date + the new programme's duration. Leave
        #    original_expected_end_date alone — the baseline is what Registry agreed to.
        previous_end = student.expected_end_date
        if new_prog.duration_months:
            student.expected_end_date = _add_months(effective, new_prog.duration_months)
        # If the new programme has no configured duration, leave expected_end_date unchanged so
        # the return still has a date to show; the warning below flags it.
        elif student.expected_end_date is None:
            warnings.append(
                f"The new programme '{new_prog.code}' has no configured duration — set duration_months on "
                "the programme or update the student's expected end date manually."
            )

        return {
            "effectiveDate": effective.isoformat(),
            "previousProgrammeId": str(event.previous_programme_id) if event.previous_programme_id else None,
            "newProgrammeId": str(new_prog.id),
            "previousProgrammeCode": old_prog.code if old_prog else None,
            "newProgrammeCode": new_prog.code,
            "crossType": cross_type,
            "milestonesCancelled": cancelled,
            "milestonesGenerated": generated,
            "previousExpectedEnd": previous_end.isoformat() if previous_end else None,
            "newExpectedEnd": student.expected_end_date.isoformat() if student.expected_end_date else None,
            "originalExpectedEnd": (
                student.original_expected_end_date.isoformat()
                if student.original_expected_end_date else None
            ),
            "warnings": warnings,
        }

    async def programme_periods_for(
        self, student: Student, *, year_start: date, year_end: date,
    ) -> list[dict]:
        """Slice the student's registration inside the given return window into per-programme
        periods, honouring every approved ``programme_change`` event on the record.

        A student with no approved programme changes yields a single period covering their whole
        registration inside the window. Each mid-window change ends the running period on the day
        before the effective date and opens a fresh one on the effective date.
        """
        start = student.start_date or year_start
        end_cap = student.expected_end_date or year_end
        events = sorted(
            [
                e for e in await self.events_for_student(student.id)
                if e.event_type is LifecycleEventType.programme_change
                and e.status is LifecycleEventStatus.approved
                and e.new_programme_id is not None
                and e.effective_date is not None
            ],
            key=lambda e: e.effective_date,
        )

        # Walk the timeline from ``start`` forward, opening a new period at each change.
        periods: list[tuple[date, date, uuid.UUID | None]] = []
        cur_from = start
        # The programme in force at ``cur_from`` — earliest change tells us what came before it.
        cur_prog = events[0].previous_programme_id if events else student.programme_id
        for ev in events:
            if ev.effective_date > cur_from:
                periods.append((cur_from, ev.effective_date, cur_prog))
            cur_from = ev.effective_date
            cur_prog = ev.new_programme_id
        periods.append((cur_from, max(end_cap, cur_from), cur_prog))

        # Clip each period to the return's academic-year window; drop anything outside it.
        out: list[dict] = []
        for p_from, p_to, prog_id in periods:
            lo = max(p_from, year_start)
            hi = min(p_to, year_end)
            if hi > lo:
                out.append({"programme_id": prog_id, "period_start": lo, "period_end": hi})
        return out

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
