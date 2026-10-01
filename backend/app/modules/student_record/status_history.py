"""Student status history — the single write path for ``student.status`` (effective dating, Phase 1).

A status is a sequence of half-open periods ``[valid_from, valid_to)``. Two operations change it:

``change``   reality changed on a date (a suspension starts, a student withdraws). The period
             covering that date is closed and a new one opens. A back-dated change runs only until
             the next recorded change, so later history is never silently overwritten. A change on
             the same day a period started replaces that period (it never actually held).
``correct``  the *record* was wrong (wrong date, wrong value). The wrong row is kept but superseded
             by a fixed copy; neighbours are adjusted so the timeline stays contiguous.

``student.status`` caches the value covering today. A future-dated change is written now but the
cache only moves when its date arrives (``refresh_due``, run by the scheduler).

Nothing here commits: callers own the transaction, as the lifecycle service does.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.models import Student, StudentStatusHistory


def today() -> date:
    """The current date. A module function so tests can move time."""
    return date.today()


def _covers(row: StudentStatusHistory, on: date) -> bool:
    return row.valid_from <= on and (row.valid_to is None or row.valid_to > on)


class StatusHistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------------- reads ----------------

    async def live_rows(self, student_id: uuid.UUID) -> list[StudentStatusHistory]:
        rows = await self.session.execute(
            select(StudentStatusHistory)
            .where(StudentStatusHistory.student_id == student_id,
                   StudentStatusHistory.superseded_by.is_(None))
            .order_by(StudentStatusHistory.valid_from)
        )
        return list(rows.scalars().all())

    async def all_rows(self, student_id: uuid.UUID) -> list[StudentStatusHistory]:
        """Live and superseded rows, oldest first — the full audit view."""
        rows = await self.session.execute(
            select(StudentStatusHistory)
            .where(StudentStatusHistory.student_id == student_id)
            .order_by(StudentStatusHistory.valid_from, StudentStatusHistory.recorded_at)
        )
        return list(rows.scalars().all())

    async def value_at(self, student_id: uuid.UUID, on: date) -> StudentStatusHistory | None:
        return next((r for r in await self.live_rows(student_id) if _covers(r, on)), None)

    async def periods(
        self, student_ids: list[uuid.UUID], window_start: date, window_end: date,
    ) -> dict[uuid.UUID, list[dict]]:
        """Live periods overlapping ``[window_start, window_end)`` for many students in one query,
        clipped to the window. ``to`` is exclusive; None means still open."""
        if not student_ids:
            return {}
        rows = await self.session.execute(
            select(StudentStatusHistory)
            .where(StudentStatusHistory.student_id.in_(student_ids),
                   StudentStatusHistory.superseded_by.is_(None),
                   StudentStatusHistory.valid_from < window_end,
                   or_(StudentStatusHistory.valid_to.is_(None),
                       StudentStatusHistory.valid_to > window_start))
            .order_by(StudentStatusHistory.student_id, StudentStatusHistory.valid_from)
        )
        out: dict[uuid.UUID, list[dict]] = {}
        for r in rows.scalars().all():
            out.setdefault(r.student_id, []).append({
                "status": r.status, "from": max(r.valid_from, window_start),
                "to": min(r.valid_to, window_end) if r.valid_to is not None else None,
                "rowId": r.id,
            })
        return out

    # ---------------- writes ----------------

    def _new_row(
        self, student: Student, status: StudentStatus, valid_from: date, valid_to: date | None, *,
        origin: str, reason: str | None, user_id: uuid.UUID | None, source_event_id: uuid.UUID | None,
    ) -> StudentStatusHistory:
        row = StudentStatusHistory(
            id=uuid.uuid4(), student_id=student.id, status=status,
            valid_from=valid_from, valid_to=valid_to, origin=origin, reason=reason,
            recorded_by_user_id=user_id, source_event_id=source_event_id,
        )
        # History belongs to the student's institution, whatever context wrote it.
        if getattr(student, "tenant_id", None) is not None:
            row.tenant_id = student.tenant_id
        self.session.add(row)
        return row

    async def initialise(
        self, student: Student, *, valid_from: date | None = None, origin: str = "initial",
        reason: str | None = None, user_id: uuid.UUID | None = None,
    ) -> StudentStatusHistory | None:
        """Open the first period with the student's current status (no-op if history exists)."""
        if await self.live_rows(student.id):
            return None
        start = valid_from or student.start_date or today()
        row = self._new_row(student, student.status, start, None, origin=origin, reason=reason,
                            user_id=user_id, source_event_id=None)
        await self.session.flush()
        return row

    async def change(
        self, student: Student, status: StudentStatus, *, effective_from: date,
        effective_to: date | None = None, reason: str | None = None,
        user_id: uuid.UUID | None = None, source_event_id: uuid.UUID | None = None,
    ) -> StudentStatusHistory:
        """Record that the student's status became ``status`` on ``effective_from`` (until
        ``effective_to`` if given, else until the next recorded change)."""
        d = effective_from
        if student.start_date is not None and d < student.start_date:
            raise WorkflowError(
                f"A status change cannot take effect before the student's start date ({student.start_date})"
            )
        if effective_to is not None and effective_to <= d:
            raise WorkflowError("The end of a status period must be after its start")

        if not await self.live_rows(student.id):
            # A student who predates status history: open their history with today's status first.
            seed_from = min(d, student.start_date) if student.start_date else d
            await self.initialise(student, valid_from=seed_from, origin="backfill",
                                  reason="Opened when the first dated change was recorded")
        rows = await self.live_rows(student.id)

        first = rows[0]
        if d < first.valid_from:
            # Earlier than anything recorded: fill the gap up to the first period.
            end = effective_to if effective_to is not None else first.valid_from
            if end != first.valid_from:
                # Past the first period it would overlap; short of it, it would leave a gap.
                raise WorkflowError(
                    f"Status history starts on {first.valid_from}; a change before that must run "
                    "up to that date (or correct the first period instead)"
                )
            new = self._new_row(student, status, d, end, origin="change", reason=reason,
                                user_id=user_id, source_event_id=source_event_id)
            await self.session.flush()
            return await self._finish(student, new)

        cover = next(r for r in rows if _covers(r, d))
        if cover.status == status:
            return cover   # already true on that date: nothing to record
        old_end = cover.valid_to
        if effective_to is not None and old_end is not None and effective_to > old_end:
            raise WorkflowError(
                f"This change would run past the next recorded change on {old_end}; "
                "record it in two steps or correct the later period"
            )

        new = self._new_row(student, status, d, effective_to if effective_to is not None else old_end,
                            origin="change", reason=reason, user_id=user_id,
                            source_event_id=source_event_id)
        if effective_to is not None and (old_end is None or effective_to < old_end):
            # A bounded change: the earlier value resumes when it ends.
            self._new_row(student, cover.status, effective_to, old_end, origin="change",
                          reason=cover.reason, user_id=user_id, source_event_id=cover.source_event_id)
        await self.session.flush()   # insert first: a supersede points at the new row
        if cover.valid_from == d:
            cover.superseded_by = new.id   # same-day change: the earlier value never held
        else:
            cover.valid_to = d             # the only in-place edit: closing a period
        await self.session.flush()
        return await self._finish(student, new)

    async def correct(
        self, row_id: uuid.UUID, *, valid_from: date | None = None,
        status: StudentStatus | None = None, reason: str, user_id: uuid.UUID | None = None,
    ) -> StudentStatusHistory:
        """Fix a row that was recorded wrongly: a new start date and/or value. The wrong row is
        superseded (kept for audit); if the start moves, the previous period's end moves with it."""
        if not (reason or "").strip():
            raise WorkflowError("A correction needs a reason")
        row = await self.session.get(StudentStatusHistory, row_id)
        if row is None:
            raise NotFoundError("Status history row not found")
        if row.superseded_by is not None:
            raise ConflictError("This row has already been corrected; correct the current version")
        student = await self.session.get(Student, row.student_id)

        rows = await self.live_rows(row.student_id)
        idx = next(i for i, r in enumerate(rows) if r.id == row.id)
        prev = rows[idx - 1] if idx > 0 else None
        new_from = valid_from or row.valid_from
        new_status = status or row.status
        if new_from == row.valid_from and new_status == row.status:
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

        fixed = self._new_row(student, new_status, new_from, row.valid_to, origin="correction",
                              reason=reason, user_id=user_id, source_event_id=row.source_event_id)
        prev_fixed = None
        if prev is not None and new_from != row.valid_from:
            prev_fixed = self._new_row(student, prev.status, prev.valid_from, new_from,
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
        """Set ``student.status`` to the value covering today. Returns True if it changed."""
        current = await self.value_at(student.id, today())
        if current is not None and student.status != current.status:
            student.status = current.status
            return True
        return False

    async def refresh_due(self) -> int:
        """Bring every cached status in line with its history for today — picks up future-dated
        changes whose date has arrived. Idempotent, so it is safe to run on every scheduler tick."""
        on = today()
        rows = await self.session.execute(
            select(Student, StudentStatusHistory.status)
            .join(StudentStatusHistory, StudentStatusHistory.student_id == Student.id)
            .where(StudentStatusHistory.superseded_by.is_(None),
                   StudentStatusHistory.valid_from <= on,
                   or_(StudentStatusHistory.valid_to.is_(None), StudentStatusHistory.valid_to > on),
                   StudentStatusHistory.status != Student.status)
        )
        changed = 0
        for student, status in rows.all():
            student.status = status
            changed += 1
        if changed:
            await self.session.flush()
        return changed

    # ---------------- invariants ----------------

    async def _finish(self, student: Student, row: StudentStatusHistory) -> StudentStatusHistory:
        self.assert_valid(await self.live_rows(student.id))
        await self.refresh_cache(student)
        return row

    @staticmethod
    def assert_valid(rows: list[StudentStatusHistory]) -> None:
        """Live periods must be well-formed, ordered, contiguous and only the last open-ended.
        PostgreSQL also enforces no-overlap with a constraint; this keeps SQLite honest too."""
        for i, r in enumerate(rows):
            if r.valid_to is not None and r.valid_to <= r.valid_from:
                raise WorkflowError(f"Status period starting {r.valid_from} ends on or before it starts")
            if i + 1 < len(rows):
                nxt = rows[i + 1]
                if r.valid_to is None:
                    raise WorkflowError(f"Status period starting {r.valid_from} is open but not the last")
                if r.valid_to != nxt.valid_from:
                    kind = "overlaps" if r.valid_to > nxt.valid_from else "leaves a gap before"
                    raise WorkflowError(f"Status period starting {r.valid_from} {kind} {nxt.valid_from}")

    # ---------------- helpers for callers ----------------

    async def previous_value(self, row: StudentStatusHistory) -> StudentStatus | None:
        """The status in force just before ``row`` started."""
        prev = next((r for r in await self.live_rows(row.student_id) if r.valid_to == row.valid_from), None)
        return prev.status if prev else None

    async def row_for_event(
        self, student_id: uuid.UUID, event_id: uuid.UUID, status: StudentStatus | None = None,
    ) -> StudentStatusHistory | None:
        """The live period an approved lifecycle event opened (optionally with a given status)."""
        return next((r for r in await self.live_rows(student_id)
                     if r.source_event_id == event_id and (status is None or r.status == status)), None)

    @staticmethod
    def out(row: StudentStatusHistory) -> dict:
        return {
            "id": str(row.id),
            "studentId": str(row.student_id),
            "status": row.status.value if hasattr(row.status, "value") else row.status,
            "validFrom": row.valid_from.isoformat(),
            "validTo": row.valid_to.isoformat() if row.valid_to else None,
            "origin": row.origin,
            "reason": row.reason,
            "sourceEventId": str(row.source_event_id) if row.source_event_id else None,
            "recordedAt": row.recorded_at.isoformat() if row.recorded_at else None,
            "recordedByUserId": str(row.recorded_by_user_id) if row.recorded_by_user_id else None,
            "supersededBy": str(row.superseded_by) if row.superseded_by else None,
        }
