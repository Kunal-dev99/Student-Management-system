"""Effective-dated student facts — the single write path for each fact and its cached value.

A fact (status, programme, study intensity) is a sequence of half-open periods
``[valid_from, valid_to)``. Two operations change it:

``change``   reality changed on a date (a suspension starts, a transfer takes effect). The period
             covering that date is closed (superseded by a closed copy, never edited in place) and a
             new one opens. A back-dated change runs only until
             the next recorded change, so later history is never silently overwritten. A change on
             the same day a period started replaces that period (it never actually held).
``correct``  the *record* was wrong (wrong date, wrong value). The wrong row is kept but superseded
             by a fixed copy; neighbours are adjusted so the timeline stays contiguous.

Each fact's current value is cached on the student row (``status``, ``programme_id``,
``study_mode``) so screens read it without a join. The cache always reflects the period covering
today: a future-dated change is written now but the cache only moves when its date arrives
(``refresh_due``, run by the scheduler).

Nothing here commits: callers own the transaction, as the lifecycle service does.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.student_record.constants import (
    DEFAULT_PART_TIME_INTENSITY_PCT,
    FULL_TIME_INTENSITY_PCT,
    StudentStatus,
    StudyMode,
)
from app.modules.student_record.models import (
    Student,
    StudentCustomValue,
    StudentCustomValueHistory,
    StudentFeeStatusHistory,
    StudentIntensityHistory,
    StudentLocationHistory,
    StudentProgrammeHistory,
    StudentStatusHistory,
    StudentUoaHistory,
    PersonUoaHistory,
    StudentExpectedEndHistory,
    StudentFeeEligibilityHistory,
    StudentOutsideUkHistory,
)
from app.modules.person.models import Person


def today() -> date:
    """The current date. A module function so tests can move time."""
    return date.today()


def _covers(row, on: date) -> bool:
    return row.valid_from <= on and (row.valid_to is None or row.valid_to > on)


def mode_for_intensity(pct: int | None) -> StudyMode:
    """Study mode is a summary of intensity: 100% is full time, anything less part time."""
    return StudyMode.full_time if (pct or 0) >= FULL_TIME_INTENSITY_PCT else StudyMode.part_time


def intensity_for_mode(mode: StudyMode | None) -> int:
    return FULL_TIME_INTENSITY_PCT if mode is StudyMode.full_time else DEFAULT_PART_TIME_INTENSITY_PCT


class FactHistoryService:
    """Generic engine; subclasses say which model, which value column and how the cache works."""
    model: type
    value_attr: str
    label: str        # used in messages, e.g. "status"
    out_key: str      # key for the value in API output
    # The record the history belongs to (a student by default; e.g. a module enrolment).
    subject_model: type = Student
    subject_attr: str = "student_id"
    subject_out_key: str = "studentId"
    subject_label: str = "student"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _subject_col(self):
        return getattr(self.model, self.subject_attr)

    @staticmethod
    def _start(subject) -> date | None:
        return getattr(subject, "start_date", None)

    # ---- per-fact hooks ----

    def initial_value(self, student: Student) -> Any:
        raise NotImplementedError

    def cache_matches(self, student: Student, value: Any) -> bool:
        raise NotImplementedError

    def apply_cache(self, student: Student, value: Any) -> None:
        raise NotImplementedError

    def _value(self, row) -> Any:
        return getattr(row, self.value_attr)

    def _out_value(self, value: Any) -> Any:
        if hasattr(value, "value"):
            return value.value
        if isinstance(value, uuid.UUID):
            return str(value)
        return value

    # ---------------- reads ----------------

    async def live_rows(self, student_id: uuid.UUID) -> list:
        m = self.model
        rows = await self.session.execute(
            select(m).where(self._subject_col() == student_id, m.superseded_by.is_(None)).order_by(m.valid_from)
        )
        return list(rows.scalars().all())

    async def all_rows(self, student_id: uuid.UUID) -> list:
        """Live and superseded rows, oldest first — the full audit view."""
        m = self.model
        rows = await self.session.execute(
            select(m).where(self._subject_col() == student_id).order_by(m.valid_from, m.recorded_at)
        )
        return list(rows.scalars().all())

    async def value_at(self, student_id: uuid.UUID, on: date):
        return next((r for r in await self.live_rows(student_id) if _covers(r, on)), None)

    async def periods(
        self, student_ids: list[uuid.UUID], window_start: date, window_end: date,
        *, known_at=None,
    ) -> dict[uuid.UUID, list[dict]]:
        """Live periods overlapping ``[window_start, window_end)`` for many students in one query,
        clipped to the window. ``to`` is exclusive; None means still open.

        ``known_at`` (a datetime) gives the periods as they were recorded at that moment instead of
        now: rows recorded later are ignored, and a row superseded later counts as live (Phase 7)."""
        if not student_ids:
            return {}
        m = self.model
        q = (select(m)
             .where(self._subject_col().in_(student_ids),
                    m.valid_from < window_end,
                    or_(m.valid_to.is_(None), m.valid_to > window_start))
             .order_by(self._subject_col(), m.valid_from))
        if known_at is None:
            rows = (await self.session.execute(q.where(m.superseded_by.is_(None)))).scalars().all()
        else:
            candidates = (await self.session.execute(q.where(m.recorded_at <= known_at))).scalars().all()
            sup_ids = {r.superseded_by for r in candidates if r.superseded_by is not None}
            known_sup = set()
            if sup_ids:
                known_sup = set((await self.session.execute(
                    select(m.id).where(m.id.in_(sup_ids), m.recorded_at <= known_at)
                )).scalars().all())
            rows = [r for r in candidates if r.superseded_by is None or r.superseded_by not in known_sup]
        out: dict[uuid.UUID, list[dict]] = {}
        for r in rows:
            out.setdefault(getattr(r, self.subject_attr), []).append({
                "value": self._value(r), "from": max(r.valid_from, window_start),
                "to": min(r.valid_to, window_end) if r.valid_to is not None else None,
                "rowId": r.id,
            })
        return out

    # ---------------- writes ----------------

    def _new_row(
        self, student: Student, value: Any, valid_from: date, valid_to: date | None, *,
        origin: str, reason: str | None, user_id: uuid.UUID | None, source_event_id: uuid.UUID | None,
        closure: bool = False,
    ):
        row = self.model(
            id=uuid.uuid4(), valid_from=valid_from, valid_to=valid_to,
            origin=origin, reason=reason, recorded_by_user_id=user_id, source_event_id=source_event_id,
            closure=closure,
        )
        setattr(row, self.subject_attr, student.id)
        setattr(row, self.value_attr, value)
        # History belongs to the student's institution, whatever context wrote it.
        if getattr(student, "tenant_id", None) is not None:
            row.tenant_id = student.tenant_id
        self.session.add(row)
        return row

    async def initialise(
        self, student: Student, *, valid_from: date | None = None, value: Any = None,
        origin: str = "initial", reason: str | None = None, user_id: uuid.UUID | None = None,
    ):
        """Open the first period with the student's current value (no-op if history exists)."""
        if await self.live_rows(student.id):
            return None
        start = valid_from or self._start(student) or today()
        row = self._new_row(student, self.initial_value(student) if value is None else value, start, None,
                            origin=origin, reason=reason, user_id=user_id, source_event_id=None)
        await self.session.flush()
        return row

    async def change(
        self, student: Student, value: Any, *, effective_from: date,
        effective_to: date | None = None, reason: str | None = None,
        user_id: uuid.UUID | None = None, source_event_id: uuid.UUID | None = None,
    ):
        """Record that the fact became ``value`` on ``effective_from`` (until ``effective_to`` if
        given, else until the next recorded change)."""
        d = effective_from
        if self._start(student) is not None and d < self._start(student):
            raise WorkflowError(
                f"A {self.label} change cannot take effect before the {self.subject_label}'s start date ({self._start(student)})"
            )
        if effective_to is not None and effective_to <= d:
            raise WorkflowError(f"The end of a {self.label} period must be after its start")

        if not await self.live_rows(student.id):
            # A student who predates this history: open it with today's value first.
            seed_from = min(d, self._start(student)) if self._start(student) else d
            await self.initialise(student, valid_from=seed_from, origin="backfill",
                                  reason="Opened when the first dated change was recorded")
        rows = await self.live_rows(student.id)

        first = rows[0]
        if d < first.valid_from:
            end = effective_to if effective_to is not None else first.valid_from
            if end != first.valid_from:
                # Past the first period it would overlap; short of it, it would leave a gap.
                raise WorkflowError(
                    f"The {self.label} history starts on {first.valid_from}; a change before that "
                    "must run up to that date (or correct the first period instead)"
                )
            new = self._new_row(student, value, d, end, origin="change", reason=reason,
                                user_id=user_id, source_event_id=source_event_id)
            await self.session.flush()
            return await self._finish(student, new)

        cover = next(r for r in rows if _covers(r, d))
        if self._value(cover) == value:
            return cover   # already true on that date: nothing to record
        old_end = cover.valid_to
        if effective_to is not None and old_end is not None and effective_to > old_end:
            raise WorkflowError(
                f"This change would run past the next recorded {self.label} change on {old_end}; "
                "record it in two steps or correct the later period"
            )

        new = self._new_row(student, value, d, effective_to if effective_to is not None else old_end,
                            origin="change", reason=reason, user_id=user_id,
                            source_event_id=source_event_id)
        if effective_to is not None and (old_end is None or effective_to < old_end):
            # A bounded change: the earlier value resumes when it ends.
            self._new_row(student, self._value(cover), effective_to, old_end, origin="change",
                          reason=cover.reason, user_id=user_id, source_event_id=cover.source_event_id)
        if cover.valid_from == d:
            await self.session.flush()     # insert first: a supersede points at the new row
            cover.superseded_by = new.id   # same-day change: the earlier value never held
        else:
            # Close the earlier period without editing it: a closed copy supersedes it, so what we
            # knew before this change (an open period) stays reconstructable (Phase 7).
            closed = self._new_row(student, self._value(cover), cover.valid_from, d,
                                   origin=cover.origin, reason=cover.reason, user_id=user_id,
                                   source_event_id=cover.source_event_id, closure=True)
            await self.session.flush()
            cover.superseded_by = closed.id
        await self.session.flush()
        return await self._finish(student, new)

    async def correct(
        self, row_id: uuid.UUID, *, valid_from: date | None = None, value: Any = None,
        reason: str, user_id: uuid.UUID | None = None,
    ):
        """Fix a row that was recorded wrongly: a new start date and/or value. The wrong row is
        superseded (kept for audit); if the start moves, the previous period's end moves with it."""
        if not (reason or "").strip():
            raise WorkflowError("A correction needs a reason")
        row = await self.session.get(self.model, row_id)
        if row is None:
            raise NotFoundError(f"{self.label.capitalize()} history row not found")
        if row.superseded_by is not None:
            raise ConflictError("This row has already been corrected; correct the current version")
        student = await self.session.get(self.subject_model, getattr(row, self.subject_attr))

        rows = await self.live_rows(getattr(row, self.subject_attr))
        idx = next(i for i, r in enumerate(rows) if r.id == row.id)
        prev = rows[idx - 1] if idx > 0 else None
        new_from = valid_from or row.valid_from
        new_value = self._value(row) if value is None else value
        if new_from == row.valid_from and new_value == self._value(row):
            raise WorkflowError("The correction doesn't change anything")
        if new_from != row.valid_from:
            if row.valid_to is not None and new_from >= row.valid_to:
                raise WorkflowError(f"The start must stay before this period's end ({row.valid_to})")
            if prev is not None and new_from <= prev.valid_from:
                raise WorkflowError(
                    f"The start must stay after the previous period's start ({prev.valid_from})"
                )
            if prev is None and self._start(student) is not None and new_from < self._start(student):
                raise WorkflowError(f"The start cannot precede the {self.subject_label}'s start date ({self._start(student)})")

        fixed = self._new_row(student, new_value, new_from, row.valid_to, origin="correction",
                              reason=reason, user_id=user_id, source_event_id=row.source_event_id)
        prev_fixed = None
        if prev is not None and new_from != row.valid_from:
            prev_fixed = self._new_row(student, self._value(prev), prev.valid_from, new_from,
                                       origin="correction", reason=reason, user_id=user_id,
                                       source_event_id=prev.source_event_id)
        await self.session.flush()
        row.superseded_by = fixed.id
        if prev_fixed is not None:
            prev.superseded_by = prev_fixed.id
        await self.session.flush()
        return await self._finish(student, fixed)

    # ---------------- cache ----------------

    async def refresh_cache(self, student: Student) -> bool:
        """Set the cached value to the one covering today. Returns True if it changed."""
        current = await self.value_at(student.id, today())
        if current is not None and not self.cache_matches(student, self._value(current)):
            self.apply_cache(student, self._value(current))
            return True
        return False

    async def refresh_due(self) -> int:
        """Bring every cached value in line with its history for today — picks up future-dated
        changes whose date has arrived. Idempotent, so it is safe to run on every scheduler tick."""
        on = today()
        m = self.model
        rows = await self.session.execute(
            select(self.subject_model, m)
            .join(m, self._subject_col() == self.subject_model.id)
            .where(m.superseded_by.is_(None), m.valid_from <= on,
                   or_(m.valid_to.is_(None), m.valid_to > on))
        )
        changed = 0
        for student, row in rows.all():
            if not self.cache_matches(student, self._value(row)):
                self.apply_cache(student, self._value(row))
                changed += 1
        if changed:
            await self.session.flush()
        return changed

    # ---------------- invariants ----------------

    async def _finish(self, student: Student, row):
        self.assert_valid(await self.live_rows(student.id))
        await self.refresh_cache(student)
        return row

    @staticmethod
    def assert_valid(rows: list) -> None:
        """Live periods must be well-formed, ordered, contiguous and only the last open-ended.
        PostgreSQL also enforces no-overlap with a constraint; this keeps SQLite honest too."""
        for i, r in enumerate(rows):
            if r.valid_to is not None and r.valid_to <= r.valid_from:
                raise WorkflowError(f"Period starting {r.valid_from} ends on or before it starts")
            if i + 1 < len(rows):
                nxt = rows[i + 1]
                if r.valid_to is None:
                    raise WorkflowError(f"Period starting {r.valid_from} is open but not the last")
                if r.valid_to != nxt.valid_from:
                    kind = "overlaps" if r.valid_to > nxt.valid_from else "leaves a gap before"
                    raise WorkflowError(f"Period starting {r.valid_from} {kind} {nxt.valid_from}")

    # ---------------- helpers for callers ----------------

    async def previous_value(self, row) -> Any:
        """The value in force just before ``row`` started."""
        prev = next((r for r in await self.live_rows(getattr(row, self.subject_attr))
                     if r.valid_to == row.valid_from), None)
        return self._value(prev) if prev else None

    async def row_for_event(self, student_id: uuid.UUID, event_id: uuid.UUID, value: Any = None):
        """The live period an approved lifecycle event opened (optionally with a given value)."""
        return next((r for r in await self.live_rows(student_id)
                     if r.source_event_id == event_id and (value is None or self._value(r) == value)), None)

    def out(self, row) -> dict:
        return {
            "id": str(row.id),
            self.subject_out_key: str(getattr(row, self.subject_attr)),
            self.out_key: self._out_value(self._value(row)),
            "validFrom": row.valid_from.isoformat(),
            "validTo": row.valid_to.isoformat() if row.valid_to else None,
            "origin": row.origin,
            "reason": row.reason,
            "sourceEventId": str(row.source_event_id) if row.source_event_id else None,
            "recordedAt": row.recorded_at.isoformat() if row.recorded_at else None,
            "recordedByUserId": str(row.recorded_by_user_id) if row.recorded_by_user_id else None,
            "supersededBy": str(row.superseded_by) if row.superseded_by else None,
            # Phase 7 — a closed copy written when the period ended (not a correction).
            "closure": bool(getattr(row, "closure", False)),
        }


class StatusHistoryService(FactHistoryService):
    """``student.status`` over time (feeds HESA SessionStatus)."""
    model = StudentStatusHistory
    value_attr = "status"
    label = "status"
    out_key = "status"

    def initial_value(self, student: Student) -> StudentStatus:
        return student.status

    def cache_matches(self, student: Student, value) -> bool:
        return student.status == value

    def apply_cache(self, student: Student, value) -> None:
        student.status = value

    async def correct(self, row_id, *, valid_from=None, status=None, value=None, reason, user_id=None):
        return await super().correct(row_id, valid_from=valid_from, value=status if status is not None else value,
                                     reason=reason, user_id=user_id)


class ProgrammeHistoryService(FactHistoryService):
    """``student.programme_id`` over time (feeds HESA StudentCourseSession)."""
    model = StudentProgrammeHistory
    value_attr = "programme_id"
    label = "programme"
    out_key = "programmeId"

    def initial_value(self, student: Student):
        return student.programme_id

    def cache_matches(self, student: Student, value) -> bool:
        return student.programme_id == value

    def apply_cache(self, student: Student, value) -> None:
        student.programme_id = value


class IntensityHistoryService(FactHistoryService):
    """Study intensity (FTE %) over time; ``student.study_mode`` caches its summary (feeds STULOAD)."""
    model = StudentIntensityHistory
    value_attr = "intensity_pct"
    label = "study intensity"
    out_key = "intensityPct"

    def initial_value(self, student: Student) -> int:
        return intensity_for_mode(student.study_mode)

    def cache_matches(self, student: Student, value) -> bool:
        return student.study_mode == mode_for_intensity(value)

    def apply_cache(self, student: Student, value) -> None:
        student.study_mode = mode_for_intensity(value)


class OptionalFactHistoryService(FactHistoryService):
    """A fact that may not be recorded yet (Phase 6). No history until the first value is given;
    the first value opens it from its own date (a gap before it just means "not recorded")."""

    async def normalise(self, value):
        """Check and normalise a value from the API (subclasses define ``validate``)."""
        return self.validate(value)

    async def initialise(self, student, *, valid_from=None, value=None, origin="initial",
                         reason=None, user_id=None):
        if value is None and self.initial_value(student) is None:
            return None
        return await super().initialise(student, valid_from=valid_from, value=value, origin=origin,
                                        reason=reason, user_id=user_id)

    async def change(self, student, value, *, effective_from, effective_to=None, reason=None,
                     user_id=None, source_event_id=None):
        if not await self.live_rows(student.id) and self.initial_value(student) is None:
            start = self._start(student)
            if start is not None and effective_from < start:
                raise WorkflowError(
                    f"A {self.label} change cannot take effect before the {self.subject_label}'s "
                    f"start date ({start})"
                )
            if effective_to is not None and effective_to <= effective_from:
                raise WorkflowError(f"The end of a {self.label} period must be after its start")
            row = self._new_row(student, value, effective_from, effective_to, origin="change",
                                reason=reason, user_id=user_id, source_event_id=source_event_id)
            await self.session.flush()
            return await self._finish(student, row)
        return await super().change(student, value, effective_from=effective_from,
                                    effective_to=effective_to, reason=reason, user_id=user_id,
                                    source_event_id=source_event_id)


# Fee status values (as captured at admission, ``application.fee_status``).
FEE_STATUSES = ("home", "overseas", "channel_islands", "unknown")


class FeeStatusHistoryService(OptionalFactHistoryService):
    """Fee status over time; ``student.fee_status`` caches today's (Phase 6)."""
    model = StudentFeeStatusHistory
    value_attr = "fee_status"
    label = "fee status"
    out_key = "feeStatus"

    def initial_value(self, student: Student):
        return student.fee_status

    def cache_matches(self, student: Student, value) -> bool:
        return student.fee_status == value

    def apply_cache(self, student: Student, value) -> None:
        student.fee_status = value

    @staticmethod
    def validate(value) -> str:
        v = str(value or "").strip().lower()
        if v not in FEE_STATUSES:
            raise WorkflowError(f"Fee status must be one of: {', '.join(FEE_STATUSES)}")
        return v


class LocationHistoryService(OptionalFactHistoryService):
    """Location of study over time; ``student.study_location`` caches today's (Phase 6)."""
    model = StudentLocationHistory
    value_attr = "study_location"
    label = "study location"
    out_key = "studyLocation"

    def initial_value(self, student: Student):
        return student.study_location

    def cache_matches(self, student: Student, value) -> bool:
        return student.study_location == value

    def apply_cache(self, student: Student, value) -> None:
        student.study_location = value

    @staticmethod
    def validate(value) -> str:
        v = str(value or "").strip()
        if not v or len(v) > 60:
            raise WorkflowError("A study location is required (up to 60 characters)")
        return v


class CustomValueHistoryService(OptionalFactHistoryService):
    """Dated values of a custom attribute with history switched on (Phase 6). The subject is the
    student's value row; ``student_custom_value.value`` caches today's."""
    model = StudentCustomValueHistory
    value_attr = "value"
    label = "attribute value"
    out_key = "value"
    subject_model = StudentCustomValue
    subject_attr = "custom_value_id"
    subject_out_key = "customValueId"
    subject_label = "attribute value"

    @staticmethod
    def _start(subject) -> date | None:
        return None   # bounded by the student's start date at the API, not here

    def initial_value(self, cv: StudentCustomValue):
        return cv.value

    def cache_matches(self, cv: StudentCustomValue, value) -> bool:
        return cv.value == value

    def apply_cache(self, cv: StudentCustomValue, value) -> None:
        cv.value = value


class _UoaChecks:
    """Shared by the student and person UOA services (Phase 9): the value is a UOA id that must
    exist and be active."""

    @staticmethod
    def validate(value) -> uuid.UUID:
        try:
            return uuid.UUID(str(value))
        except (ValueError, TypeError):
            raise WorkflowError("Choose a unit of assessment") from None

    async def normalise(self, value) -> uuid.UUID:
        from app.modules.student_record.models import UnitOfAssessment

        uoa_id = self.validate(value)
        uoa = await self.session.get(UnitOfAssessment, uoa_id)
        if uoa is None:
            raise NotFoundError("Unit of assessment not found")
        if not uoa.is_active:
            raise WorkflowError(f"UOA {uoa.code} is no longer in use")
        return uoa_id


class StudentUoaHistoryService(_UoaChecks, OptionalFactHistoryService):
    """A student's unit of assessment over time; ``student.uoa_id`` caches today's (Phase 9)."""
    model = StudentUoaHistory
    value_attr = "uoa_id"
    label = "unit of assessment"
    out_key = "uoaId"

    def initial_value(self, student: Student):
        return student.uoa_id

    def cache_matches(self, student: Student, value) -> bool:
        return student.uoa_id == value

    def apply_cache(self, student: Student, value) -> None:
        student.uoa_id = value


class PersonUoaHistoryService(_UoaChecks, OptionalFactHistoryService):
    """A person's (supervisor's) unit of assessment over time; ``person.uoa_id`` caches today's.
    The subject is the person, so one change applies to every student they supervise (Phase 9)."""
    model = PersonUoaHistory
    value_attr = "uoa_id"
    label = "unit of assessment"
    out_key = "uoaId"
    subject_model = Person
    subject_attr = "person_id"
    subject_out_key = "personId"
    subject_label = "person"

    @staticmethod
    def _start(subject) -> date | None:
        return None

    def initial_value(self, person):
        return person.uoa_id

    def cache_matches(self, person, value) -> bool:
        return person.uoa_id == value

    def apply_cache(self, person, value) -> None:
        person.uoa_id = value


class ExpectedEndHistoryService(OptionalFactHistoryService):
    """The expected end date as held over time (Phase 10; HESA ENGEXPECTEDENDDATE).

    A period means "from this day, we expected the student to finish on X". Extensions,
    suspensions, intensity and programme changes recompute ``student.expected_end_date``; ``sync``
    then records the new expectation from the day it changed."""
    model = StudentExpectedEndHistory
    value_attr = "expected_end_date"
    label = "expected end date"
    out_key = "expectedEndDate"

    def initial_value(self, student: Student):
        return student.expected_end_date

    def cache_matches(self, student: Student, value) -> bool:
        return student.expected_end_date == value

    def apply_cache(self, student: Student, value) -> None:
        student.expected_end_date = value

    async def sync(self, student: Student, *, user_id: uuid.UUID | None = None,
                   reason: str | None = None, source_event_id: uuid.UUID | None = None):
        """Record ``student.expected_end_date`` if it differs from what history holds for today.
        The change is dated today (or the start date, for a student who hasn't started)."""
        value = student.expected_end_date
        if value is None:
            return None
        rows = await self.live_rows(student.id)
        on = today()
        if student.start_date is not None and on < student.start_date:
            on = student.start_date
        held = next((r for r in rows if _covers(r, on)), None)
        if held is not None and held.expected_end_date == value:
            return held
        return await self.change(student, value, effective_from=on, reason=reason, user_id=user_id,
                                 source_event_id=source_event_id)


# Fee eligibility values (HESA FEEELIG categories; mapped to codes by a return transform).
FEE_ELIGIBILITIES = ("eligible", "not_eligible", "not_required")


class FeeEligibilityHistoryService(OptionalFactHistoryService):
    """Fee eligibility over time (Phase 10; HESA FEEELIG)."""
    model = StudentFeeEligibilityHistory
    value_attr = "fee_eligibility"
    label = "fee eligibility"
    out_key = "feeEligibility"

    def initial_value(self, student: Student):
        return student.fee_eligibility

    def cache_matches(self, student: Student, value) -> bool:
        return student.fee_eligibility == value

    def apply_cache(self, student: Student, value) -> None:
        student.fee_eligibility = value

    @staticmethod
    def validate(value) -> str:
        v = str(value or "").strip().lower()
        if v not in FEE_ELIGIBILITIES:
            raise WorkflowError(f"Fee eligibility must be one of: {', '.join(FEE_ELIGIBILITIES)}")
        return v


class OutsideUkHistoryService(OptionalFactHistoryService):
    """Whether the student studies primarily outside the UK, over time (Phase 10; HESA ENGPRINONUK)."""
    model = StudentOutsideUkHistory
    value_attr = "primarily_outside_uk"
    label = "study primarily outside the UK"
    out_key = "primarilyOutsideUk"

    def initial_value(self, student: Student):
        return student.primarily_outside_uk

    def cache_matches(self, student: Student, value) -> bool:
        return student.primarily_outside_uk == value

    def apply_cache(self, student: Student, value) -> None:
        student.primarily_outside_uk = value

    @staticmethod
    def validate(value) -> bool:
        v = str(value).strip().lower()
        if v in ("true", "yes", "y", "1"):
            return True
        if v in ("false", "no", "n", "0"):
            return False
        raise WorkflowError("Say yes or no")


# Facts every student carries; the optional ones stay empty until a value is recorded.
FACT_SERVICES = (StatusHistoryService, ProgrammeHistoryService, IntensityHistoryService,
                 FeeStatusHistoryService, LocationHistoryService, StudentUoaHistoryService,
                 ExpectedEndHistoryService, FeeEligibilityHistoryService, OutsideUkHistoryService)
# Dated student facts set directly (not through a lifecycle event), by API name.
DIRECT_FACTS = {"fee-status": FeeStatusHistoryService, "study-location": LocationHistoryService,
                "uoa": StudentUoaHistoryService, "fee-eligibility": FeeEligibilityHistoryService,
                "outside-uk": OutsideUkHistoryService}


async def initialise_all(session: AsyncSession, student: Student, *, valid_from: date | None = None,
                         origin: str = "initial", reason: str | None = None) -> None:
    """Open every fact's history for a new student."""
    for svc in FACT_SERVICES:
        await svc(session).initialise(student, valid_from=valid_from, origin=origin, reason=reason)
    # Phase 8b — the student is pinned to the programme version in force when they start (CMA).
    from app.modules.student_record.programme_versions import ProgrammeVersionService
    await ProgrammeVersionService(session).ensure_pin(student, on=valid_from or student.start_date)


async def refresh_all_due(session: AsyncSession) -> int:
    return sum([await svc(session).refresh_due()
                for svc in (*FACT_SERVICES, CustomValueHistoryService, PersonUoaHistoryService)])
