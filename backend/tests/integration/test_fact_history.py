"""Effective dating, Phase 2 — programme and intensity history, and the return reading them.

What must hold:
- a programme transfer takes effect on its date: a future-dated one leaves ``programme_id`` alone
  until the day, then the scheduler moves it
- intensity is dated history; study mode is its cached summary and also moves on the date
- a mode change no longer rewrites earlier intensity history
- the return reads history: one record per programme period with inclusive, non-overlapping
  dates; STULOAD = intensity × days actually studying ÷ days in the year (suspension counts zero);
  intensity and status as they stood at the end of each period
- the backfill rebuilds programme and intensity history and agrees with the cached values
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import app  # noqa: F401  registers every model
from app.modules.exports.statutory import StatutoryEngine
from app.modules.person.models import Person
from app.modules.student_record import fact_history
from app.modules.student_record.constants import (
    LifecycleEventStatus,
    LifecycleEventType,
    StudentStatus,
    StudyMode,
)
from app.modules.student_record.fact_backfill import (
    backfill_programme_and_intensity,
    build_segments,
    check_programme_and_intensity,
)
from app.modules.student_record.fact_history import (
    IntensityHistoryService,
    ProgrammeHistoryService,
    initialise_all,
    refresh_all_due,
)
from app.modules.student_record.lifecycle import LifecycleService
from app.modules.student_record.models import (
    Programme,
    Student,
    StudentIntensityHistory,
    StudentLifecycleEvent,
    StudentProgrammeHistory,
)

START = date(2026, 8, 1)
END = date(2030, 7, 31)


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    ids = {}
    async with sm() as s:
        mphil = Programme(name="MPhil Oncology", code="MPHIL"); phd = Programme(name="PhD Oncology", code="PHD")
        s.add_all([mphil, phd]); await s.flush()
        ids["mphil"], ids["phd"] = mphil.id, phd.id
        person = Person(given_name="Ana", family_name="Lee"); s.add(person); await s.flush()
        st = Student(person_id=person.id, student_ref="PGR-ED2", programme_id=mphil.id,
                     start_date=START, expected_end_date=END, original_expected_end_date=END,
                     study_mode=StudyMode.full_time, status=StudentStatus.active)
        s.add(st); await s.flush()
        await initialise_all(s, st)
        ids["student"] = st.id
        await s.commit()
    yield ids, sm
    await eng.dispose()


@pytest.fixture
def clock(monkeypatch):
    state = {"today": date(2026, 9, 1)}
    monkeypatch.setattr(fact_history, "today", lambda: state["today"])
    return state


async def _approve(sm, sid, **kw):
    async with sm() as s:
        lc = LifecycleService(s)
        ev = await lc.request_event(sid, reason="test", **kw)
        await lc.approve_event(ev.id, approver_user_id=None)
        return ev.id


async def _student(sm, sid):
    async with sm() as s:
        return await s.get(Student, sid)


# --------------------------------------------------------------------------------------
# Programme and intensity history
# --------------------------------------------------------------------------------------

async def test_future_transfer_waits_for_its_date(ctx, clock):
    ids, sm = ctx
    await _approve(sm, ids["student"], event_type=LifecycleEventType.programme_change,
                   start_date=date(2027, 3, 1), new_programme_id=ids["phd"])
    assert (await _student(sm, ids["student"])).programme_id == ids["mphil"]   # not yet

    clock["today"] = date(2027, 3, 1)
    async with sm() as s:
        assert await refresh_all_due(s) >= 1
        await s.commit()
    assert (await _student(sm, ids["student"])).programme_id == ids["phd"]
    async with sm() as s:
        rows = await ProgrammeHistoryService(s).live_rows(ids["student"])
        assert [(r.programme_id, r.valid_from, r.valid_to) for r in rows] == [
            (ids["mphil"], START, date(2027, 3, 1)), (ids["phd"], date(2027, 3, 1), None)]


async def test_future_mode_change_waits_and_keeps_earlier_intensity(ctx, clock):
    ids, sm = ctx
    await _approve(sm, ids["student"], event_type=LifecycleEventType.intensity_change,
                   start_date=date(2026, 8, 15), intensity_pct=80)
    assert (await _student(sm, ids["student"])).study_mode is StudyMode.part_time   # 80% is part time

    await _approve(sm, ids["student"], event_type=LifecycleEventType.mode_change,
                   start_date=date(2026, 12, 1), new_mode=StudyMode.full_time)
    assert (await _student(sm, ids["student"])).study_mode is StudyMode.part_time   # not yet

    async with sm() as s:
        rows = await IntensityHistoryService(s).live_rows(ids["student"])
        # The earlier 80% period is intact (the old code rebuilt it from the new mode).
        assert [(r.intensity_pct, r.valid_from, r.valid_to) for r in rows] == [
            (100, START, date(2026, 8, 15)), (80, date(2026, 8, 15), date(2026, 12, 1)),
            (100, date(2026, 12, 1), None)]
        st = await s.get(Student, ids["student"])
        periods = await LifecycleService(s).intensity_periods(st)
        assert [p["pct"] for p in periods] == [100, 80, 100]

    clock["today"] = date(2026, 12, 2)
    async with sm() as s:
        await refresh_all_due(s); await s.commit()
    assert (await _student(sm, ids["student"])).study_mode is StudyMode.full_time


# --------------------------------------------------------------------------------------
# The return
# --------------------------------------------------------------------------------------

async def test_golden_return_for_2026_27(ctx, clock):
    """Suspended Nov–Dec, transferred MPhil -> PhD on 1 Mar, down to 50% on 1 Apr."""
    ids, sm = ctx
    sid = ids["student"]
    clock["today"] = date(2027, 9, 1)   # the year is over: report what happened
    await _approve(sm, sid, event_type=LifecycleEventType.suspension,
                   start_date=date(2026, 11, 1), end_date=date(2027, 1, 1))
    async with sm() as s:
        await LifecycleService(s).record_return(sid, returned_on=date(2027, 1, 1))
    await _approve(sm, sid, event_type=LifecycleEventType.programme_change,
                   start_date=date(2027, 3, 1), new_programme_id=ids["phd"])
    await _approve(sm, sid, event_type=LifecycleEventType.intensity_change,
                   start_date=date(2027, 4, 1), intensity_pct=50)

    async with sm() as s:
        records = await StatutoryEngine(s).build_records("2026/27")
    mine = [r for r in records if r["student"]["ref"].startswith("PGR-ED2")]
    assert [(r["programme"]["code"], r["student"]["startDate"], r["student"]["expectedEndDate"])
            for r in mine] == [
        ("MPHIL", date(2026, 8, 1), date(2027, 2, 28)),   # inclusive: the day before PhD starts
        ("PHD", date(2027, 3, 1), date(2027, 7, 31)),
    ]
    mphil, phd = (r["student"] for r in mine)
    # Aug–Oct (92 days) + Jan–Feb (59 days) studying at 100%; the 61 suspended days count zero.
    assert mphil["fteLoad"] == round(100 * 151 / 365, 1) == 41.4
    # March at 100% (31 days) + April–July at 50% (122 days).
    assert phd["fteLoad"] == round((100 * 31 + 50 * 122) / 365, 1) == 25.2
    assert mphil["intensityPct"] == 100 and phd["intensityPct"] == 50   # as at each period's end
    assert phd["mode"] == "part_time"
    assert mphil["status"] == "active" and phd["status"] == "active"


async def test_return_without_a_year_reads_today(ctx, clock):
    ids, sm = ctx
    await _approve(sm, ids["student"], event_type=LifecycleEventType.intensity_change,
                   start_date=date(2027, 1, 1), intensity_pct=60)
    async with sm() as s:
        records = await StatutoryEngine(s).build_records()
    rec = next(r["student"] for r in records if r["student"]["ref"] == "PGR-ED2")
    # The approved change is dated in the future: today the student is still full time.
    assert rec["intensityPct"] == 100 and rec["mode"] == "full_time"
    assert rec["fteLoad"] is None   # load needs a reporting year


async def test_full_year_full_time_is_100(ctx, clock):
    ids, sm = ctx
    clock["today"] = date(2027, 9, 1)
    async with sm() as s:
        records = await StatutoryEngine(s).build_records("2026/27")
    rec = next(r["student"] for r in records if r["student"]["ref"] == "PGR-ED2")
    assert rec["fteLoad"] == 100.0


# --------------------------------------------------------------------------------------
# Backfill
# --------------------------------------------------------------------------------------

def test_build_segments_pure():
    t = date(2027, 6, 1)
    segs = build_segments(start=START, base="A", today=t, cache_ok=lambda v: v == "B", cache_value="B",
                          changes=[(date(2027, 3, 1), "B", "e1")])
    assert segs == [(START, date(2027, 3, 1), "A", None), (date(2027, 3, 1), None, "B", "e1")]
    # Old rules applied a future transfer immediately: the cache wins from today.
    segs = build_segments(start=START, base="A", today=t, cache_ok=lambda v: v == "B", cache_value="B",
                          changes=[(date(2027, 9, 1), "B", "e2")])
    assert segs == [(START, t, "A", None), (t, None, "B", None)]


async def test_backfill_rebuilds_programme_and_intensity(ctx):
    ids, sm = ctx
    async with sm() as s:
        # A student who predates dated history, with an approved transfer and mode change.
        person = Person(given_name="Old", family_name="Record"); s.add(person); await s.flush()
        st = Student(person_id=person.id, student_ref="PGR-OLD", programme_id=ids["phd"],
                     start_date=START, study_mode=StudyMode.part_time, status=StudentStatus.active)
        s.add(st); await s.flush()
        s.add_all([
            StudentLifecycleEvent(student_id=st.id, event_type=LifecycleEventType.programme_change,
                                  status=LifecycleEventStatus.approved, start_date=date(2027, 2, 1),
                                  effective_date=date(2027, 2, 1), previous_programme_id=ids["mphil"],
                                  new_programme_id=ids["phd"], reason="transfer"),
            StudentLifecycleEvent(student_id=st.id, event_type=LifecycleEventType.mode_change,
                                  status=LifecycleEventStatus.approved, start_date=date(2026, 10, 1),
                                  previous_mode=StudyMode.full_time, new_mode=StudyMode.part_time,
                                  reason="mode"),
        ])
        await s.commit()
        old_id = st.id
    today = date(2027, 6, 1)
    async with sm.kw["bind"].begin() as conn:
        counts = await conn.run_sync(lambda c: backfill_programme_and_intensity(c, today=today))
        assert counts["programmeStudents"] == 1 and counts["intensityStudents"] == 1   # ctx student had history
        assert await conn.run_sync(lambda c: check_programme_and_intensity(c, today=today)) == []
    async with sm() as s:
        progs = (await s.execute(select(StudentProgrammeHistory).where(
            StudentProgrammeHistory.student_id == old_id).order_by(StudentProgrammeHistory.valid_from))).scalars().all()
        assert [(p.programme_id, p.valid_from, p.valid_to) for p in progs] == [
            (ids["mphil"], START, date(2027, 2, 1)), (ids["phd"], date(2027, 2, 1), None)]
        ints = (await s.execute(select(StudentIntensityHistory).where(
            StudentIntensityHistory.student_id == old_id).order_by(StudentIntensityHistory.valid_from))).scalars().all()
        assert [(i.intensity_pct, i.valid_from, i.valid_to) for i in ints] == [
            (100, START, date(2026, 10, 1)), (50, date(2026, 10, 1), None)]
