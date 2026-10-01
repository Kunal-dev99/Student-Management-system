"""Rebuild student status history from data that predates it (effective dating, Phase 1).

Run once by the ``ed1_status_history`` migration, and reusable from tests. It works on a plain
synchronous SQLAlchemy ``Connection`` with Core table stubs (not the ORM models) so it keeps
working however the models evolve.

What it can reconstruct honestly:
  * every approved suspension becomes a ``suspended`` period ``[start, actual_end)`` (open if the
    student hasn't returned), with ``active`` between them;
  * a completed student with a graduation date becomes ``completed`` from that date;
  * otherwise the current status runs from the end of the last suspension (or the start date).
If the rebuilt timeline disagrees with the cached ``student.status`` today (e.g. a future-start
suspension approved under the old rules, which suspended immediately), the cache wins from today:
the timeline is cut at today and the cached status recorded from today. Every row is marked
``origin = 'backfill'``. Students who already have history are skipped, so it is safe to re-run.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection

_student = sa.table(
    "student", sa.column("id", sa.Uuid()), sa.column("tenant_id", sa.Uuid()),
    sa.column("status", sa.String()), sa.column("start_date", sa.Date()),
    sa.column("created_at", sa.DateTime(timezone=True)),
)
_event = sa.table(
    "student_lifecycle_event", sa.column("id", sa.Uuid()), sa.column("student_id", sa.Uuid()),
    sa.column("event_type", sa.String()), sa.column("status", sa.String()),
    sa.column("start_date", sa.Date()), sa.column("actual_end_date", sa.Date()),
)
_completion = sa.table(
    "completion", sa.column("student_id", sa.Uuid()), sa.column("graduation_date", sa.Date()),
)
_history = sa.table(
    "student_status_history", sa.column("id", sa.Uuid()), sa.column("tenant_id", sa.Uuid()),
    sa.column("student_id", sa.Uuid()), sa.column("status", sa.String()),
    sa.column("valid_from", sa.Date()), sa.column("valid_to", sa.Date()),
    sa.column("origin", sa.String()), sa.column("reason", sa.Text()),
    sa.column("source_event_id", sa.Uuid()), sa.column("recorded_at", sa.DateTime(timezone=True)),
    sa.column("superseded_by", sa.Uuid()),
)


def _val(v) -> str:
    return v.value if hasattr(v, "value") else str(v)


def _txt(col):
    """Compare an enum column as text: PostgreSQL has no enum = varchar operator."""
    return sa.cast(col, sa.String())


def _status(conn: Connection, value: str):
    """A status value typed for the column (PostgreSQL won't assign varchar to an enum)."""
    if conn.dialect.name == "postgresql":
        return sa.cast(sa.literal(value, sa.Text()), postgresql.ENUM(name="student_status", create_type=False))
    return value


def build_timeline(
    *, status: str, start: date, suspensions: list[tuple], graduation_date: date | None, today: date,
) -> list[tuple]:
    """Pure function: (valid_from, valid_to, status, source_event_id) segments, contiguous."""
    segs: list[list] = []
    cur = start
    for ev_id, s_start, s_end in sorted(suspensions, key=lambda x: x[1]):
        s_start = max(s_start, cur)
        if s_end is not None and s_end <= s_start:
            continue
        if s_start > cur:
            segs.append([cur, s_start, "active", None])
        segs.append([s_start, s_end, "suspended", ev_id])
        if s_end is None:
            cur = None
            break
        cur = s_end
    if cur is not None:
        if status == "completed" and graduation_date is not None and graduation_date > cur:
            segs.append([cur, graduation_date, "active", None])
            segs.append([graduation_date, None, "completed", None])
        else:
            segs.append([cur, None, status, None])

    def at(day: date):
        return next((s for s in segs if s[0] <= day and (s[1] is None or s[1] > day)), None)

    covering = at(today)
    if segs and segs[0][0] <= today and (covering is None or covering[2] != status):
        # The cached status is the truth for today: cut the rebuilt timeline at today.
        kept = []
        for s in segs:
            if s[0] >= today:
                continue
            if s[1] is None or s[1] > today:
                s = [s[0], today, s[2], s[3]]
            kept.append(s)
        kept.append([today, None, status, None])
        segs = kept
    return [tuple(s) for s in segs if s[1] is None or s[1] > s[0]]


def backfill_status_history(conn: Connection, today: date | None = None) -> dict:
    today = today or date.today()
    have = {r[0] for r in conn.execute(sa.select(_history.c.student_id).distinct())}
    susp: dict = {}
    for ev_id, sid, s_start, s_end in conn.execute(
        sa.select(_event.c.id, _event.c.student_id, _event.c.start_date, _event.c.actual_end_date)
        .where(_txt(_event.c.event_type) == "suspension", _txt(_event.c.status) == "approved")
    ):
        susp.setdefault(sid, []).append((ev_id, s_start, s_end))
    grads = {sid: g for sid, g in conn.execute(
        sa.select(_completion.c.student_id, _completion.c.graduation_date)
    ) if g is not None}

    now = datetime.now(timezone.utc)
    students = rows = 0
    for sid, tenant_id, status, start, created in conn.execute(
        sa.select(_student.c.id, _student.c.tenant_id, _txt(_student.c.status),
                  _student.c.start_date, _student.c.created_at)
    ):
        if sid in have:
            continue
        begin = start or (created.date() if created else today)
        segs = build_timeline(status=_val(status), start=begin, suspensions=susp.get(sid, []),
                              graduation_date=grads.get(sid), today=today)
        for valid_from, valid_to, st, ev_id in segs:
            conn.execute(_history.insert().values(
                id=uuid.uuid4(), tenant_id=tenant_id, student_id=sid, status=_status(conn, st),
                valid_from=valid_from, valid_to=valid_to, origin="backfill",
                reason="Rebuilt from records that predate status history",
                source_event_id=ev_id, recorded_at=now,
            ))
            rows += 1
        students += 1
    return {"students": students, "rows": rows}


def check_status_history(conn: Connection, today: date | None = None) -> list:
    """Students whose cached status disagrees with their history today (should be empty)."""
    today = today or date.today()
    live: dict = {}
    for sid, st, vf, vt in conn.execute(
        sa.select(_history.c.student_id, _txt(_history.c.status), _history.c.valid_from, _history.c.valid_to)
        .where(_history.c.superseded_by.is_(None))
    ):
        live.setdefault(sid, []).append((vf, vt, _val(st)))
    bad = []
    for sid, status in conn.execute(sa.select(_student.c.id, _txt(_student.c.status))):
        periods = live.get(sid)
        if not periods:
            bad.append((sid, "no history"))
            continue
        cover = next((p for p in periods if p[0] <= today and (p[1] is None or p[1] > today)), None)
        if cover is None:
            if min(p[0] for p in periods) > today:
                continue   # starts in the future: today's cached status stands alone
            bad.append((sid, "no period covers today"))
        elif cover[2] != _val(status):
            bad.append((sid, f"history says {cover[2]}, cache says {_val(status)}"))
    return bad
