"""Rebuild programme and intensity history from data that predates it (effective dating, Phase 2).

Run once by the ``ed2_programme_intensity_history`` migration and reusable from tests. Like
``status_backfill``, it works on a plain synchronous ``Connection`` with Core table stubs.

Programme: approved programme changes become periods ``[effective, next change)``; before the first
change the student was on that change's previous programme (else their current one).
Intensity: approved intensity changes set the %, approved mode changes set the mode's default %
(full time 100, part time 50); before the first change, that change's previous value applies.

If the rebuilt timeline disagrees with the cached value today (under the old rules an approved
transfer or mode change applied immediately, even when dated in the future), the cache wins from
today: the timeline is cut at today and the cached value recorded from today. Every row is marked
``origin = 'backfill'``; students who already have history are skipped, so re-running is safe.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import sqlalchemy as sa
from sqlalchemy.engine import Connection

FULL_TIME_PCT = 100
PART_TIME_PCT = 50


def pct_for_mode(mode: str | None) -> int:
    return FULL_TIME_PCT if mode == "full_time" else PART_TIME_PCT


def mode_for_pct(pct: int | None) -> str:
    return "full_time" if (pct or 0) >= FULL_TIME_PCT else "part_time"


_student = sa.table(
    "student", sa.column("id", sa.Uuid()), sa.column("tenant_id", sa.Uuid()),
    sa.column("programme_id", sa.Uuid()), sa.column("study_mode", sa.String()),
    sa.column("start_date", sa.Date()), sa.column("created_at", sa.DateTime(timezone=True)),
)
_event = sa.table(
    "student_lifecycle_event", sa.column("id", sa.Uuid()), sa.column("student_id", sa.Uuid()),
    sa.column("event_type", sa.String()), sa.column("status", sa.String()),
    sa.column("start_date", sa.Date()), sa.column("effective_date", sa.Date()),
    sa.column("previous_programme_id", sa.Uuid()), sa.column("new_programme_id", sa.Uuid()),
    sa.column("previous_intensity_pct", sa.Integer()), sa.column("intensity_pct", sa.Integer()),
    sa.column("previous_mode", sa.String()), sa.column("new_mode", sa.String()),
)


def _history(name: str, value_col: sa.ColumnClause):
    return sa.table(
        name, sa.column("id", sa.Uuid()), sa.column("tenant_id", sa.Uuid()),
        sa.column("student_id", sa.Uuid()), value_col,
        sa.column("valid_from", sa.Date()), sa.column("valid_to", sa.Date()),
        sa.column("origin", sa.String()), sa.column("reason", sa.Text()),
        sa.column("source_event_id", sa.Uuid()), sa.column("recorded_at", sa.DateTime(timezone=True)),
        sa.column("superseded_by", sa.Uuid()),
    )


_prog_hist = _history("student_programme_history", sa.column("programme_id", sa.Uuid()))
_int_hist = _history("student_intensity_history", sa.column("intensity_pct", sa.Integer()))


def _txt(col):
    """Compare an enum column as text: PostgreSQL has no enum = varchar operator."""
    return sa.cast(col, sa.String())


def build_segments(*, start: date, base, changes: list[tuple], today: date,
                   cache_ok, cache_value) -> list[tuple]:
    """Pure function: contiguous (valid_from, valid_to, value, source_event_id) segments.

    ``changes`` are (effective_date, value, event_id). ``cache_ok(value)`` says whether a value agrees
    with the cached one; if the value covering today doesn't, the cache wins from today with
    ``cache_value``."""
    segs: list[list] = [[start, None, base, None]]
    for eff, value, ev_id in sorted(changes, key=lambda c: c[0]):
        eff = max(eff, start)
        last = segs[-1]
        if eff == last[0]:
            last[2], last[3] = value, ev_id   # same day: the later change wins
        else:
            last[1] = eff
            segs.append([eff, None, value, ev_id])
    cover = next((s for s in segs if s[0] <= today and (s[1] is None or s[1] > today)), None)
    if segs[0][0] <= today and (cover is None or not cache_ok(cover[2])):
        kept = []
        for s in segs:
            if s[0] >= today:
                continue
            if s[1] is None or s[1] > today:
                s = [s[0], today, s[2], s[3]]
            kept.append(s)
        kept.append([today, None, cache_value, None])
        segs = kept
    return [tuple(s) for s in segs if s[1] is None or s[1] > s[0]]


def _approved(conn: Connection, event_type: str) -> dict:
    out: dict = {}
    for row in conn.execute(
        sa.select(_event).where(_txt(_event.c.event_type) == event_type,
                                _txt(_event.c.status) == "approved")
    ).mappings():
        out.setdefault(row["student_id"], []).append(dict(row))
    return out


def _val(v) -> str | None:
    return None if v is None else (v.value if hasattr(v, "value") else str(v))


def backfill_programme_and_intensity(conn: Connection, today: date | None = None) -> dict:
    today = today or date.today()
    have_prog = {r[0] for r in conn.execute(sa.select(_prog_hist.c.student_id).distinct())}
    have_int = {r[0] for r in conn.execute(sa.select(_int_hist.c.student_id).distinct())}
    transfers = _approved(conn, "programme_change")
    intensity = _approved(conn, "intensity_change")
    modes = _approved(conn, "mode_change")
    now = datetime.now(timezone.utc)
    reason = "Rebuilt from records that predate dated history"
    counts = {"programmeStudents": 0, "programmeRows": 0, "intensityStudents": 0, "intensityRows": 0}

    for sid, tenant_id, prog_id, mode, start, created in conn.execute(
        sa.select(_student.c.id, _student.c.tenant_id, _student.c.programme_id,
                  _txt(_student.c.study_mode), _student.c.start_date, _student.c.created_at)
    ):
        begin = start or (created.date() if created else today)

        if sid not in have_prog:
            evs = sorted(transfers.get(sid, []), key=lambda e: e["effective_date"] or e["start_date"])
            base = (evs[0]["previous_programme_id"] if evs else None) or prog_id
            segs = build_segments(
                start=begin, base=base, today=today,
                changes=[(e["effective_date"] or e["start_date"], e["new_programme_id"], e["id"]) for e in evs],
                cache_ok=lambda v: v == prog_id, cache_value=prog_id,
            )
            for vf, vt, value, ev_id in segs:
                conn.execute(_prog_hist.insert().values(
                    id=uuid.uuid4(), tenant_id=tenant_id, student_id=sid, programme_id=value,
                    valid_from=vf, valid_to=vt, origin="backfill", reason=reason,
                    source_event_id=ev_id, recorded_at=now))
                counts["programmeRows"] += 1
            counts["programmeStudents"] += 1

        if sid not in have_int:
            evs = sorted(
                [("i", e) for e in intensity.get(sid, []) if e["intensity_pct"]]
                + [("m", e) for e in modes.get(sid, []) if e["new_mode"]],
                key=lambda x: x[1]["start_date"],
            )
            if evs:
                kind, first = evs[0]
                base = (first["previous_intensity_pct"] if kind == "i" else None) or (
                    pct_for_mode(_val(first["previous_mode"])) if kind == "m" and first["previous_mode"]
                    else pct_for_mode(mode))
            else:
                base = pct_for_mode(mode)
            changes = [(e["start_date"], e["intensity_pct"] if k == "i" else pct_for_mode(_val(e["new_mode"])), e["id"])
                       for k, e in evs]
            segs = build_segments(
                start=begin, base=base, changes=changes, today=today,
                cache_ok=lambda v: mode_for_pct(v) == mode, cache_value=pct_for_mode(mode),
            )
            for vf, vt, value, ev_id in segs:
                conn.execute(_int_hist.insert().values(
                    id=uuid.uuid4(), tenant_id=tenant_id, student_id=sid, intensity_pct=value,
                    valid_from=vf, valid_to=vt, origin="backfill", reason=reason,
                    source_event_id=ev_id, recorded_at=now))
                counts["intensityRows"] += 1
            counts["intensityStudents"] += 1
    return counts


def check_programme_and_intensity(conn: Connection, today: date | None = None) -> list:
    """Students whose cached programme / study mode disagrees with their history today."""
    today = today or date.today()

    def covering(table, col):
        out: dict = {}
        for sid, value, vf, vt in conn.execute(
            sa.select(table.c.student_id, col, table.c.valid_from, table.c.valid_to)
            .where(table.c.superseded_by.is_(None))
        ):
            out.setdefault(sid, []).append((vf, vt, value))
        return out

    progs = covering(_prog_hist, _prog_hist.c.programme_id)
    ints = covering(_int_hist, _int_hist.c.intensity_pct)
    bad = []
    for sid, prog_id, mode in conn.execute(
        sa.select(_student.c.id, _student.c.programme_id, _txt(_student.c.study_mode))
    ):
        for name, periods, ok in (("programme", progs.get(sid), lambda v: v == prog_id),
                                  ("intensity", ints.get(sid), lambda v: mode_for_pct(v) == mode)):
            if not periods:
                bad.append((sid, f"no {name} history"))
                continue
            cover = next((p for p in periods if p[0] <= today and (p[1] is None or p[1] > today)), None)
            if cover is None:
                if min(p[0] for p in periods) > today:
                    continue   # starts in the future
                bad.append((sid, f"no {name} period covers today"))
            elif not ok(cover[2]):
                bad.append((sid, f"{name} history disagrees with the cached value"))
    return bad
