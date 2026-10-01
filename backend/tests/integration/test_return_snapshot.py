"""Effective dating, Phase 7 — HESA snapshot: "as at" a date and "as known at" a moment.

What must hold (Demo 2, item 1.12):
- the return takes each value as it stood on the snapshot date, not the latest
  (Alistair's example: Live in August, Interrupted in March, back in June)
- anything entered after the snapshot moment is left out, even if back-dated, so late changes
  don't bleed into a return that was already produced; students enrolled later are left out too
- funding / supervision ended after the moment still count as open then
- a period that ends is superseded by a closed copy, never edited in place
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import app  # noqa: F401  registers every model
from app.modules.exports.statutory import StatutoryEngine
from app.modules.funding.constants import FundingType
from app.modules.funding.repository import FundingRepository
from app.modules.funding.schemas import ArrangementCreate
from app.modules.funding.service import FundingService
from app.modules.person.models import Person
from app.modules.student_record import fact_history
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.fact_history import StatusHistoryService, initialise_all
from app.modules.student_record.models import Programme, Student

START = date(2024, 10, 1)
YEAR = "2025/26"


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        prog = Programme(name="PhD Oncology", code="PHD"); s.add(prog)
        person = Person(given_name="Ana", family_name="Lee"); s.add(person); await s.flush()
        st = Student(person_id=person.id, student_ref="PGR-ED7", programme_id=prog.id,
                     start_date=START, expected_end_date=date(2028, 9, 30),
                     study_mode=StudyMode.full_time, status=StudentStatus.active)
        s.add(st); await s.flush()
        await initialise_all(s, st)
        await s.commit()
        sid = st.id
    yield sid, sm
    await eng.dispose()


@pytest.fixture
def clock(monkeypatch):
    state = {"today": date(2026, 10, 1)}
    monkeypatch.setattr(fact_history, "today", lambda: state["today"])
    return state


async def _record(sm, **kw) -> dict:
    async with sm() as s:
        records = await StatutoryEngine(s).build_records(YEAR, **kw)
    return next((r for r in records if r["student"]["ref"] == "PGR-ED7"), None)


async def test_status_as_at_the_snapshot_date(ctx, clock):
    """Alistair's example: Live in August, Interrupted in March, back in June."""
    sid, sm = ctx
    async with sm() as s:
        st = await s.get(Student, sid)
        hist = StatusHistoryService(s)
        await hist.change(st, StudentStatus.suspended, effective_from=date(2026, 3, 1))
        await hist.change(st, StudentStatus.active, effective_from=date(2026, 6, 1))
        await s.commit()
    assert (await _record(sm, as_at=date(2025, 8, 1)))["student"]["status"] == "active"
    assert (await _record(sm, as_at=date(2026, 4, 1)))["student"]["status"] == "suspended"
    assert (await _record(sm))["student"]["status"] == "active"   # default: the year end


async def test_back_dated_entries_after_the_moment_dont_bleed_in(ctx, clock):
    sid, sm = ctx
    async with sm() as s:
        st = await s.get(Student, sid)
        await FundingService(FundingRepository(s)).create_arrangement(st.id, ArrangementCreate(
            funding_type=FundingType.research_council, valid_from=START))
        await s.commit()
    frozen = datetime.now(timezone.utc)

    # After the snapshot moment: a suspension back-dated into the year, funding ended
    # back-dated, and a new student enrolled.
    async with sm() as s:
        st = await s.get(Student, sid)
        await StatusHistoryService(s).change(st, StudentStatus.suspended, effective_from=date(2026, 2, 1),
                                             reason="Reported late")
        [fa] = await FundingRepository(s).arrangements_for_student(sid)
        await FundingService(FundingRepository(s)).end(fa.id, on=date(2026, 3, 1))
        late = Person(given_name="Cy", family_name="Late"); s.add(late); await s.flush()
        s.add(Student(person_id=late.id, student_ref="PGR-LATE", start_date=START,
                      study_mode=StudyMode.full_time, status=StudentStatus.active))
        await s.commit()

    now_rec = await _record(sm, as_at=date(2026, 4, 1))
    assert now_rec["student"]["status"] == "suspended"
    assert now_rec["fundingPeriods"][0]["validTo"] == date(2026, 2, 28)

    then = await _record(sm, as_at=date(2026, 4, 1), known_at=frozen)
    assert then["student"]["status"] == "active"                   # the late entry doesn't bleed in
    assert then["fundingPeriods"][0]["validTo"] is None            # funding still open as known then
    assert [x["status"] for x in then["statusHistory"]] == ["active"]
    async with sm() as s:
        refs = {r["student"]["ref"] for r in await StatutoryEngine(s).build_records(YEAR, known_at=frozen)}
    assert "PGR-LATE" not in refs


async def test_ending_a_period_never_edits_it_in_place(ctx, clock):
    sid, sm = ctx
    async with sm() as s:
        st = await s.get(Student, sid)
        hist = StatusHistoryService(s)
        [first] = await hist.live_rows(sid)
        await hist.change(st, StudentStatus.writing_up, effective_from=date(2026, 5, 1))
        await s.commit()
        old = await s.get(type(first), first.id)
        assert old.valid_to is None and old.superseded_by is not None   # untouched, superseded
        closed = await s.get(type(first), old.superseded_by)
        assert closed.closure is True and (closed.valid_from, closed.valid_to) == (START, date(2026, 5, 1))
        assert [(r.status, r.closure) for r in await hist.live_rows(sid)] == [
            (StudentStatus.active, True), (StudentStatus.writing_up, False)]
