"""Effective-dated student facts — the single write path for each fact and its cached value.

A fact (status, programme, study intensity) is a sequence of half-open periods
``[valid_from, valid_to)``. Two operations change it:

``change``   reality changed on a date (a suspension starts, a transfer takes effect). The period
             covering that date is closed and a new one opens. A back-dated change runs only until
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
    StudentIntensityHistory,
    StudentProgrammeHistory,
    StudentStatusHistory,
)


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

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
            select(m).where(m.student_id == student_id, m.superseded_by.is_(None)).order_by(m.valid_from)
        )
        return list(rows.scalars().all())

    async def all_rows(self, student_id: uuid.UUID) -> list:
        """Live and superseded rows, oldest first — the full audit view."""
        m = self.model
        rows = await self.session.execute(
            select(m).where(m.student_id == student_id).order_by(m.valid_from, m.recorded_at)
        )
        return list(rows.scalars().all())

    async def value_at(self, student_id: uuid.UUID, on: date):
        return next((r for r in await self.live_rows(student_id) if _covers(r, on)), None)

    async def periods(
        self, student_ids: list[uuid.UUID], window_start: date, window_end: date,
    ) -> dict[uuid.UUID, list[dict]]:
        """Live periods overlapping ``[window_start, window_end)`` for many students in one query,
        clipped to the window. ``to`` is exclusive; None means still open."""
        if not student_ids:
            return {}
        m = self.model
        rows = await self.session.execute(
            select(m)
            .where(m.student_id.in_(student_ids), m.superseded_by.is_(None),
                   m.valid_from < window_end,
                   or_(m.valid_to.is_(None), m.valid_to > window_start))
            .order_by(m.student_id, m.valid_from)
        )
        out: dict[uuid.UUID, list[dict]] = {}
        for r in rows.scalars().all():
            out.setdefault(r.student_id, []).append({
                "value": self._value(r), "from": max(r.valid_from, window_start),
                "to": min(r.valid_to, window_end) if r.valid_to is not None else None,
                "rowId": r.id,
            })
        return out

    # ---------------- writes ----------------

    def _new_row(
        self, student: Student, value: Any, valid_from: date, valid_to: date | None, *,
        origin: str, reason: str | None, user_id: uuid.UUID | None, source_event_id: uuid.UUID | None,
    ):
        row = self.model(
            id=uuid.uuid4(), student_id=student.id, valid_from=valid_from, valid_to=valid_to,
            origin=origin, reason=reason, recorded_by_user_id=user_id, source_event_id=source_event_id,
        )
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
        start = valid_from or student.start_date or today()
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
        if student.start_date is not None and d < student.start_date:
            raise WorkflowError(
                f"A {self.label} change cannot take effect before the student's start date ({student.start_date})"
            )
        if effective_to is not None and effective_to <= d:
            raise WorkflowError(f"The end of a {self.label} period must be after its start")

        if not await self.live_rows(student.id):
            # A student who predates this history: open it with today's value first.
            seed_from = min(d, student.start_date) if student.start_date else d
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
        await self.session.flush()   # insert first: a supersede points at the new row
        if cover.valid_from == d:
            cover.superseded_by = new.id   # same-day change: the earlier value never held
        else:
            cover.valid_to = d             # the only in-place edit: closing a period
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
        student = await self.session.get(Student, row.student_id)

        rows = await self.live_rows(row.student_id)
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
            if prev is None and student.start_date is not None and new_from < student.start_date:
                raise WorkflowError(f"The start cannot precede the student's start date ({student.start_date})")

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
            select(Student, m)
            .join(m, m.student_id == Student.id)
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
        prev = next((r for r in await self.live_rows(row.student_id) if r.valid_to == row.valid_from), None)
        return self._value(prev) if prev else None

    async def row_for_event(self, student_id: uuid.UUID, event_id: uuid.UUID, value: Any = None):
        """The live period an approved lifecycle event opened (optionally with a given value)."""
        return next((r for r in await self.live_rows(student_id)
                     if r.source_event_id == event_id and (value is None or self._value(r) == value)), None)

    def out(self, row) -> dict:
        return {
            "id": str(row.id),
            "studentId": str(row.student_id),
            self.out_key: self._out_value(self._value(row)),
            "validFrom": row.valid_from.isoformat(),
            "validTo": row.valid_to.isoformat() if row.valid_to else None,
            "origin": row.origin,
            "reason": row.reason,
            "sourceEventId": str(row.source_event_id) if row.source_event_id else None,
            "recordedAt": row.recorded_at.isoformat() if row.recorded_at else None,
            "recordedByUserId": str(row.recorded_by_user_id) if row.recorded_by_user_id else None,
            "supersededBy": str(row.superseded_by) if row.superseded_by else None,
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


FACT_SERVICES = (StatusHistoryService, ProgrammeHistoryService, IntensityHistoryService)


async def initialise_all(session: AsyncSession, student: Student, *, valid_from: date | None = None,
                         origin: str = "initial", reason: str | None = None) -> None:
    """Open every fact's history for a new student."""
    for svc in FACT_SERVICES:
        await svc(session).initialise(student, valid_from=valid_from, origin=origin, reason=reason)


async def refresh_all_due(session: AsyncSession) -> int:
    return sum([await svc(session).refresh_due() for svc in FACT_SERVICES])
