"""Effective dating, Phase 5 — retrospective changes, the history timeline, the as-of view and the
back-dating limit.

What must hold:
- a change about to be recorded warns when it reaches a signed-off return's year, not otherwise
- after sign-off, changes recorded later inside the return's year are listed; earlier ones and
  backfilled rows are not; unsigning clears the baseline
- the history timeline merges every dated fact and marks the retrospective ones
- the as-of view shows the record as it stood on a past date
- dates before the open reporting year need the history-correction permission
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.errors import PermissionError as AppPermissionError
from app.core.principal import Principal
from app.db.base import Base
from app.main import app  # noqa: F401  registers every model
from app.modules.exports.models import ReportProfile
from app.modules.funding.constants import FundingType
from app.modules.funding.repository import FundingRepository
from app.modules.funding.schemas import ArrangementCreate
from app.modules.funding.service import FundingService
from app.modules.person.models import Person
from app.modules.student_record import fact_history
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.fact_history import StatusHistoryService, initialise_all
from app.modules.student_record.models import Programme, Student
from app.modules.student_record.periods import (
    BACKDATE_PERMISSION,
    assert_backdate_allowed,
    open_year_start,
)
from app.modules.student_record.retrospective import changes_since_signoff, warnings_for
from app.modules.student_record.timeline import StudentTimeline
from app.modules.supervision.constants import SupervisorRole
from app.modules.supervision.repository import SupervisionRepository
from app.modules.supervision.service import SupervisionService

START = date(2025, 10, 1)


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    ids = {}
    async with sm() as s:
        prog = Programme(name="PhD Oncology", code="PHD"); s.add(prog)
        person = Person(given_name="Ana", family_name="Lee")
        dr = Person(given_name="Alice", family_name="Arden")
        s.add_all([person, dr]); await s.flush()
        st = Student(person_id=person.id, student_ref="PGR-ED5", programme_id=prog.id,
                     start_date=START, expected_end_date=date(2029, 9, 30),
                     study_mode=StudyMode.full_time, status=StudentStatus.active)
        s.add(st); await s.flush()
        await initialise_all(s, st)
        # The 2025/26 return, signed off a week ago.
        profile = ReportProfile(code="HESA_STUDENT", name="HESA Student", academic_year="2025/26",
                                signed_off_at=datetime.now(timezone.utc) - timedelta(days=7))
        s.add(profile); await s.flush()
        ids.update(student=st.id, profile=profile.id, dr=dr.id)
        await s.commit()
    yield ids, sm
    await eng.dispose()


@pytest.fixture
def clock(monkeypatch):
    state = {"today": date(2026, 10, 1)}
    monkeypatch.setattr(fact_history, "today", lambda: state["today"])
    return state


def _principal(*perms: str) -> Principal:
    return Principal(user_id=uuid.uuid4(), email="t@example.com", permissions=list(perms))


# --------------------------------------------------------------------------------------
# Before the change: warnings
# --------------------------------------------------------------------------------------

async def test_warns_only_when_the_change_reaches_a_signed_off_year(ctx, clock):
    ids, sm = ctx
    async with sm() as s:
        st = await s.get(Student, ids["student"])
        hit = await warnings_for(s, st, date(2026, 3, 12))
        assert [w["academicYear"] for w in hit] == ["2025/26"]
        assert "12 Mar 2026" in hit[0]["message"] and "may need resubmitting" in hit[0]["message"]
        # Inside the open year only: nothing signed off covers it.
        assert await warnings_for(s, st, date(2026, 9, 1)) == []
        # A bounded period that ends before the year starts doesn't reach it either.
        assert await warnings_for(s, st, date(2025, 1, 1), date(2025, 8, 1)) == []


async def test_no_warning_for_an_unsigned_return(ctx, clock):
    ids, sm = ctx
    async with sm() as s:
        p = await s.get(ReportProfile, ids["profile"])
        p.signed_off_at = None
        await s.commit()
        st = await s.get(Student, ids["student"])
        assert await warnings_for(s, st, date(2026, 3, 12)) == []


# --------------------------------------------------------------------------------------
# After the change: what moved since sign-off
# --------------------------------------------------------------------------------------

async def test_lists_changes_recorded_after_sign_off(ctx, clock):
    ids, sm = ctx
    async with sm() as s:
        st = await s.get(Student, ids["student"])
        # Back-dated suspension into the signed-off year, recorded now.
        await StatusHistoryService(s).change(st, StudentStatus.suspended, effective_from=date(2026, 3, 12),
                                             reason="Medical, reported late")
        await FundingService(FundingRepository(s)).create_arrangement(st.id, ArrangementCreate(
            funding_type=FundingType.self_funded, valid_from=date(2026, 1, 1)))
        await s.commit()
    async with sm() as s:
        out = await changes_since_signoff(s, ids["profile"])
    assert out["signedOff"] is True
    [student] = out["students"]
    assert student["studentRef"] == "PGR-ED5"
    facts = sorted((c["fact"], c["value"], c["validFrom"]) for c in student["changes"])
    assert ("status", "suspended", "2026-03-12") in facts
    assert ("funding", "self_funded", "2026-01-01") in facts


async def test_rows_recorded_before_sign_off_and_backfills_are_ignored(ctx, clock):
    ids, sm = ctx
    async with sm() as s:
        # Move the sign-off to now: everything in the fixture was recorded before it.
        p = await s.get(ReportProfile, ids["profile"])
        p.signed_off_at = datetime.now(timezone.utc) + timedelta(seconds=1)
        await s.commit()
    async with sm() as s:
        out = await changes_since_signoff(s, ids["profile"])
    assert out["changeCount"] == 0 and out["students"] == []


# --------------------------------------------------------------------------------------
# History timeline and as-of
# --------------------------------------------------------------------------------------

async def test_history_merges_facts_and_marks_retrospective(ctx, clock):
    ids, sm = ctx
    async with sm() as s:
        st = await s.get(Student, ids["student"])
        await StatusHistoryService(s).change(st, StudentStatus.suspended, effective_from=date(2026, 3, 12))
        await StatusHistoryService(s).change(st, StudentStatus.active, effective_from=date(2026, 6, 1))
        await SupervisionService(SupervisionRepository(s)).assign(
            st.id, ids["dr"], SupervisorRole.primary, valid_from=START, max_supervisees=10)
        await s.commit()
    async with sm() as s:
        h = await StudentTimeline(s).history(ids["student"])
    facts = {e["fact"] for e in h["entries"]}
    assert {"status", "programme", "intensity", "supervision"} <= facts
    statuses = [(e["value"], e["validFrom"], e["validTo"]) for e in h["entries"] if e["fact"] == "status"]
    assert statuses == [("active", "2025-10-01", "2026-03-12"), ("suspended", "2026-03-12", "2026-06-01"),
                        ("active", "2026-06-01", None)]
    susp = next(e for e in h["entries"] if e["value"] == "suspended")
    assert [r["academicYear"] for r in susp["retrospective"]] == ["2025/26"]
    assert h["retrospectiveCount"] >= 1
    assert h["entries"] == sorted(h["entries"], key=lambda e: e["validFrom"])


async def test_as_of_shows_the_record_on_a_past_date(ctx, clock):
    ids, sm = ctx
    async with sm() as s:
        st = await s.get(Student, ids["student"])
        await StatusHistoryService(s).change(st, StudentStatus.suspended, effective_from=date(2026, 3, 12))
        sv = SupervisionService(SupervisionRepository(s))
        rel = await sv.assign(st.id, ids["dr"], SupervisorRole.primary, valid_from=START, max_supervisees=10)
        await sv.end(rel.id, "left", on=date(2026, 5, 1))
        await s.commit()
    async with sm() as s:
        tl = StudentTimeline(s)
        then = await tl.as_of(ids["student"], date(2026, 4, 1))
        now = await tl.as_of(ids["student"], date(2026, 9, 1))
        before = await tl.as_of(ids["student"], date(2025, 9, 1))
    assert then["status"] == "suspended" and then["programmeName"] == "PhD Oncology"
    assert [x["name"] for x in then["supervisors"]] == ["Alice Arden"]
    assert now["supervisors"] == [] and now["status"] == "suspended"
    assert before["beforeStart"] is True and before["status"] is None


# --------------------------------------------------------------------------------------
# Back-dating limit
# --------------------------------------------------------------------------------------

def test_open_year_start():
    assert open_year_start(date(2026, 10, 1)) == date(2026, 8, 1)
    assert open_year_start(date(2027, 7, 31)) == date(2026, 8, 1)
    assert open_year_start(date(2026, 8, 1)) == date(2026, 8, 1)


def test_backdating_before_the_open_year_needs_permission(clock):
    plain = _principal("student.write")
    assert_backdate_allowed(date(2026, 8, 1), plain, what="This change")      # inside the open year
    assert_backdate_allowed(None, plain, what="This change")                  # today by default
    assert_backdate_allowed(date(2026, 3, 1), None, what="This change")       # internal call
    with pytest.raises(AppPermissionError, match="before the open reporting year"):
        assert_backdate_allowed(date(2026, 7, 31), plain, what="This change")
    assert_backdate_allowed(date(2026, 3, 1), _principal(BACKDATE_PERMISSION), what="This change")
