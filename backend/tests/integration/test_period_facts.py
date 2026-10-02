"""Effective dating, Phase 4 — funding and supervision periods, and the return's child lists.

What must hold:
- funding changes and ends can be back-dated (not yet future-dated) and can't precede the start
- changing supervisor ends one and starts the next on the same day, in the same role
- the same supervisor can't have overlapping periods for one student
- the return takes the funding in force in each period (funding that ended during the year is
  no longer dropped), shows supervision, and carries child lists: status changes, modules,
  funding periods and supervisors, with inclusive dates
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.errors import ConflictError, WorkflowError
from app.db.base import Base
from app.main import app  # noqa: F401  registers every model
from app.modules.exports.statutory import StatutoryEngine
from app.modules.funding.constants import FundingType
from app.modules.funding.models import FundingSource
from app.modules.funding.repository import FundingRepository
from app.modules.funding.schemas import ArrangementCreate, ChangeRequest
from app.modules.funding.service import FundingService
from app.modules.person.models import Person
from app.modules.student_record import fact_history
from app.modules.student_record.constants import LifecycleEventType, StudentStatus, StudyMode
from app.modules.student_record.fact_history import initialise_all
from app.modules.student_record.lifecycle import LifecycleService
from app.modules.student_record.models import Programme, Student
from app.modules.supervision.constants import SupervisorRole
from app.modules.supervision.repository import SupervisionRepository
from app.modules.supervision.service import SupervisionService
from app.modules.taught.constants import ModuleEnrolmentStatus
from app.modules.taught.models import ModuleEnrolment, TaughtModule
from app.modules.taught.module_history import ModuleStatusHistoryService

START = date(2026, 8, 1)


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    ids = {}
    async with sm() as s:
        prog = Programme(name="PhD Oncology", code="PHD"); s.add(prog); await s.flush()
        src = FundingSource(name="MRC"); s.add(src)
        st_person = Person(given_name="Ana", family_name="Lee")
        dr_a = Person(given_name="Alice", family_name="Arden")
        dr_b = Person(given_name="Bob", family_name="Brook")
        s.add_all([st_person, dr_a, dr_b]); await s.flush()
        st = Student(person_id=st_person.id, student_ref="PGR-ED4", programme_id=prog.id,
                     start_date=START, expected_end_date=date(2030, 7, 31),
                     study_mode=StudyMode.full_time, status=StudentStatus.active)
        s.add(st); await s.flush()
        await initialise_all(s, st)
        ids.update(student=st.id, programme=prog.id, source=src.id, dr_a=dr_a.id, dr_b=dr_b.id)
        await s.commit()
    yield ids, sm
    await eng.dispose()


@pytest.fixture
def clock(monkeypatch):
    state = {"today": date(2027, 9, 1)}
    monkeypatch.setattr(fact_history, "today", lambda: state["today"])
    return state


def _funding(s):
    return FundingService(FundingRepository(s))


def _supervision(s):
    return SupervisionService(SupervisionRepository(s))


# --------------------------------------------------------------------------------------
# Funding
# --------------------------------------------------------------------------------------

async def test_back_dated_funding_change_and_end(ctx, clock):
    ids, sm = ctx
    async with sm() as s:
        a = await _funding(s).create_arrangement(ids["student"], ArrangementCreate(
            funding_type=FundingType.research_council, funding_source_id=ids["source"], valid_from=START))
        new = await _funding(s).change(a.id, ChangeRequest(
            funding_type=FundingType.self_funded, effective_date=date(2027, 2, 1)))
        old = await FundingRepository(s).get(a.id)
        assert (old.valid_from, old.valid_to) == (START, date(2027, 2, 1))
        assert new.valid_from == date(2027, 2, 1)
        ended = await _funding(s).end(new.id, on=date(2027, 6, 1))
        assert ended.valid_to == date(2027, 6, 1)


async def test_funding_dates_are_checked(ctx, clock):
    ids, sm = ctx
    async with sm() as s:
        a = await _funding(s).create_arrangement(ids["student"], ArrangementCreate(
            funding_type=FundingType.research_council, valid_from=START))
        with pytest.raises(WorkflowError, match="future"):
            await _funding(s).change(a.id, ChangeRequest(
                funding_type=FundingType.self_funded, effective_date=date(2027, 12, 1)))
        with pytest.raises(WorkflowError, match="before the period started"):
            await _funding(s).end(a.id, on=date(2026, 7, 1))


# --------------------------------------------------------------------------------------
# Supervision
# --------------------------------------------------------------------------------------

async def test_replace_supervisor_on_a_date(ctx, clock):
    ids, sm = ctx
    async with sm() as s:
        sv = _supervision(s)
        first = await sv.assign(ids["student"], ids["dr_a"], SupervisorRole.primary,
                                valid_from=START, max_supervisees=10)
        second = await sv.replace(first.id, ids["dr_b"], reason="Dr Arden left", on=date(2027, 1, 1))
        old = await SupervisionRepository(s).get(first.id)
        assert (old.valid_to, old.end_reason) == (date(2027, 1, 1), "Dr Arden left")
        assert (second.valid_from, second.role, second.supervisor_person_id) == (
            date(2027, 1, 1), SupervisorRole.primary, ids["dr_b"])
        with pytest.raises(WorkflowError, match="reason"):
            await sv.replace(second.id, ids["dr_a"], reason=" ")


async def test_same_supervisor_cannot_overlap(ctx, clock):
    ids, sm = ctx
    async with sm() as s:
        sv = _supervision(s)
        rel = await sv.assign(ids["student"], ids["dr_a"], SupervisorRole.primary,
                              valid_from=START, max_supervisees=10)
        await sv.end(rel.id, "paused", on=date(2027, 1, 1))
        with pytest.raises(ConflictError):   # back-dated into the earlier period
            await sv.assign(ids["student"], ids["dr_a"], SupervisorRole.primary,
                            valid_from=date(2026, 12, 1), max_supervisees=10)
        again = await sv.assign(ids["student"], ids["dr_a"], SupervisorRole.primary,
                                valid_from=date(2027, 3, 1), max_supervisees=10)
        assert again.valid_from == date(2027, 3, 1)


# --------------------------------------------------------------------------------------
# The return
# --------------------------------------------------------------------------------------

async def test_return_reads_funding_supervision_and_child_lists(ctx, clock):
    ids, sm = ctx
    sid = ids["student"]
    async with sm() as s:
        a = await _funding(s).create_arrangement(sid, ArrangementCreate(
            funding_type=FundingType.research_council, funding_source_id=ids["source"],
            valid_from=START, contribution_pct=100))
        await _funding(s).end(a.id, on=date(2027, 3, 1))           # ended during the year
        rel = await _supervision(s).assign(sid, ids["dr_a"], SupervisorRole.primary,
                                           valid_from=START, max_supervisees=10)
        await _supervision(s).replace(rel.id, ids["dr_b"], reason="handover", on=date(2027, 1, 1))
        # A module taken during the year, withdrawn in May.
        mod = TaughtModule(programme_id=ids["programme"], code="RM701", title="Research Methods", credits=15)
        s.add(mod); await s.flush()
        e = ModuleEnrolment(student_id=sid, module_id=mod.id, academic_year="2026/27",
                            status=ModuleEnrolmentStatus.enrolled, start_date=date(2026, 10, 1),
                            end_date=date(2027, 7, 31))
        s.add(e); await s.flush()
        hist = ModuleStatusHistoryService(s)
        await hist.initialise(e)
        await hist.change(e, ModuleEnrolmentStatus.withdrawn, effective_from=date(2027, 5, 1))
        e.end_date = date(2027, 5, 1)
        await s.commit()
    async with sm() as s:
        lc = LifecycleService(s)
        ev = await lc.request_event(sid, event_type=LifecycleEventType.suspension, reason="Medical",
                                    start_date=date(2026, 11, 1), end_date=date(2027, 1, 1))
        await lc.approve_event(ev.id, approver_user_id=None)
    async with sm() as s:
        await LifecycleService(s).record_return(sid, returned_on=date(2027, 1, 1))

    async with sm() as s:
        records = await StatutoryEngine(s).build_records("2026/27")
    rec = next(r for r in records if r["student"]["ref"] == "PGR-ED4")

    # Funding ended in March is still reported for the year (the old return dropped it).
    assert rec["funding"]["type"] == "research_council" and rec["funding"]["source"] == "MRC"
    assert rec["fundingPeriods"] == [{
        "type": "research_council", "source": "MRC", "contributionPct": 100, "amount": None,
        "validFrom": START, "validTo": date(2027, 2, 28)}]
    # Supervision as at the end of the year, plus both supervisors in the period.
    assert rec["supervision"] == {"primaryName": "Bob Brook", "supervisorCount": 1,
                                  "primaryUoa": None}   # Phase 9: no UOA recorded here
    assert [(x["name"], x["validFrom"], x["validTo"]) for x in rec["supervisors"]] == [
        ("Alice Arden", START, date(2026, 12, 31)), ("Bob Brook", date(2027, 1, 1), None)]
    # SessionStatus-style changes, with inclusive dates.
    assert [(x["status"], x["validFrom"], x["validTo"]) for x in rec["statusHistory"]] == [
        ("active", START, date(2026, 10, 31)), ("suspended", date(2026, 11, 1), date(2026, 12, 31)),
        ("active", date(2027, 1, 1), None)]
    # ModuleInstance-style module, with its status as at the end of the year.
    assert [(m["code"], m["startDate"], m["endDate"], m["status"]) for m in rec["modules"]] == [
        ("RM701", date(2026, 10, 1), date(2027, 5, 1), "withdrawn")]
