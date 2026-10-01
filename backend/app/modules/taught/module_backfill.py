"""Give existing module enrolments dates and a status history (effective dating, Phase 3).

Run once by the ``ed3_module_enrolment_history`` migration and reusable from tests (plain
synchronous ``Connection`` + Core table stubs, like the other backfills).

Dates the enrolment doesn't have yet default to its academic year (1 Aug - 31 Jul), clipped to the
student's start and expected end. The status history is one period with the current status from
the start date: older records don't say when a module was withdrawn or completed, so no earlier
change is invented. Rows are marked ``origin = 'backfill'``; already-dated enrolments with history
are skipped, so re-running is safe.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection

_enrolment = sa.table(
    "module_enrolment", sa.column("id", sa.Uuid()), sa.column("tenant_id", sa.Uuid()),
    sa.column("student_id", sa.Uuid()), sa.column("academic_year", sa.String()),
    sa.column("status", sa.String()), sa.column("start_date", sa.Date()), sa.column("end_date", sa.Date()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
_student = sa.table(
    "student", sa.column("id", sa.Uuid()), sa.column("start_date", sa.Date()),
    sa.column("expected_end_date", sa.Date()),
)
_history = sa.table(
    "module_enrolment_status_history", sa.column("id", sa.Uuid()), sa.column("tenant_id", sa.Uuid()),
    sa.column("module_enrolment_id", sa.Uuid()), sa.column("status", sa.String()),
    sa.column("valid_from", sa.Date()), sa.column("valid_to", sa.Date()),
    sa.column("origin", sa.String()), sa.column("reason", sa.Text()),
    sa.column("recorded_at", sa.DateTime(timezone=True)), sa.column("superseded_by", sa.Uuid()),
)


def _txt(col):
    return sa.cast(col, sa.String())


def _status(conn: Connection, value: str):
    if conn.dialect.name == "postgresql":
        return sa.cast(sa.literal(value, sa.Text()),
                       postgresql.ENUM(name="module_enrolment_status", create_type=False))
    return value


def default_dates(academic_year: str | None, student_start: date | None,
                  student_end: date | None) -> tuple[date | None, date | None]:
    head = (academic_year or "").split("/", 1)[0].strip()
    if len(head) != 4 or not head.isdigit():
        return student_start, None
    y = int(head)
    start, end = date(y, 8, 1), date(y + 1, 7, 31)
    if student_start is not None:
        start = max(start, student_start)
    if student_end is not None:
        end = min(end, student_end)
    return start, (end if end >= start else None)


def backfill_module_enrolments(conn: Connection, today: date | None = None) -> dict:
    today = today or date.today()
    have = {r[0] for r in conn.execute(sa.select(_history.c.module_enrolment_id).distinct())}
    students = {sid: (s, e) for sid, s, e in conn.execute(
        sa.select(_student.c.id, _student.c.start_date, _student.c.expected_end_date))}
    now = datetime.now(timezone.utc)
    dated = rows = 0
    for eid, tenant_id, sid, year, status, start, end, created in conn.execute(
        sa.select(_enrolment.c.id, _enrolment.c.tenant_id, _enrolment.c.student_id,
                  _enrolment.c.academic_year, _txt(_enrolment.c.status), _enrolment.c.start_date,
                  _enrolment.c.end_date, _enrolment.c.created_at)
    ):
        if start is None:
            s_start, s_end = students.get(sid, (None, None))
            start, d_end = default_dates(year, s_start, s_end)
            end = end or d_end
            if start is None:
                start = created.date() if created else today
            conn.execute(_enrolment.update().where(_enrolment.c.id == eid)
                         .values(start_date=start, end_date=end))
            dated += 1
        if eid not in have:
            conn.execute(_history.insert().values(
                id=uuid.uuid4(), tenant_id=tenant_id, module_enrolment_id=eid,
                status=_status(conn, status), valid_from=start, valid_to=None, origin="backfill",
                reason="Rebuilt from records that predate dated module history", recorded_at=now,
            ))
            rows += 1
    return {"enrolmentsDated": dated, "historyRows": rows}


def check_module_enrolments(conn: Connection, today: date | None = None) -> list:
    """Enrolments whose cached status disagrees with their history today (should be empty)."""
    today = today or date.today()
    live: dict = {}
    for eid, st, vf, vt in conn.execute(
        sa.select(_history.c.module_enrolment_id, _txt(_history.c.status), _history.c.valid_from,
                  _history.c.valid_to).where(_history.c.superseded_by.is_(None))
    ):
        live.setdefault(eid, []).append((vf, vt, st))
    bad = []
    for eid, status in conn.execute(sa.select(_enrolment.c.id, _txt(_enrolment.c.status))):
        periods = live.get(eid)
        if not periods:
            bad.append((eid, "no history"))
            continue
        cover = next((p for p in periods if p[0] <= today and (p[1] is None or p[1] > today)), None)
        if cover is None:
            if min(p[0] for p in periods) > today:
                continue
            bad.append((eid, "no period covers today"))
        elif cover[2] != status:
            bad.append((eid, f"history says {cover[2]}, cache says {status}"))
    return bad
