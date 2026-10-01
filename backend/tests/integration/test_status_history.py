"""Effective dating, Phase 1 — student status history.

What must hold:
- every student's status is a contiguous run of half-open periods; live periods never overlap
- ``student.status`` always equals the period covering today
- a dated change takes effect on its date: a future-dated one leaves today's status alone until
  the scheduler applies it on the day
- returning from a suspension restores the status the student had before it (not always active)
- writing up / withdrawal / termination are approved lifecycle events with an effective date
- status, mode and programme can't be edited directly any more (409)
- a correction supersedes the wrong row (kept for audit) and keeps the timeline contiguous;
  it needs ``student.history.correct``
- the backfill rebuilds history from approved suspensions and agrees with the cached status
"""
from __future__ import annotations

import random
import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.errors import WorkflowError
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record import fact_history
from app.modules.student_record.constants import (
    LifecycleEventStatus,
    LifecycleEventType,
    StudentStatus,
    StudyMode,
)
from app.modules.student_record.models import (
    Programme,
    Student,
    StudentLifecycleEvent,
    StudentStatusHistory,
)
from app.modules.student_record.status_backfill import (
    backfill_status_history,
    build_timeline,
    check_status_history,
)
from app.modules.student_record.status_history import StatusHistoryService

START = date(2026, 1, 1)
END = date(2029, 1, 1)


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    ids = {}
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        pgr = Role(name="PGR Administrator"); s.add(pgr); await s.flush()
        await s.refresh(pgr, ["permissions"]); pgr.permissions = list(perms.values())
        admin = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(admin); await s.flush(); await s.refresh(admin, ["roles"]); admin.roles = [role, pgr]

        # May request and approve lifecycle changes, but NOT correct history.
        officer_role = Role(name="PGR Officer"); s.add(officer_role); await s.flush()
        await s.refresh(officer_role, ["permissions"])
        officer_role.permissions = [perms["student.read"], perms["student.write"],
                                    perms["student.lifecycle.approve"]]
        officer = User(email="o@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(officer); await s.flush(); await s.refresh(officer, ["roles"]); officer.roles = [officer_role]

        prog = Programme(name="PhD", code="PHD"); s.add(prog); await s.flush()
        ids["programme"] = str(prog.id)
        person = Person(given_name="Sam", family_name="Rao"); s.add(person); await s.flush()
        # Created directly, like a student who predates status history (no rows yet).
        student = Student(person_id=person.id, student_ref="PGR-HIST", programme_id=prog.id,
                          start_date=START, expected_end_date=END,
                          study_mode=StudyMode.full_time, status=StudentStatus.active)
        s.add(student); await s.flush()
        ids["student"] = str(student.id)
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        async def token(email):
            r = await c.post("/api/v1/auth/login", json={"email": email, "password": "pw"})
            return {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, token, ids, sm
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.fixture
def clock(monkeypatch):
    """Move the history service's notion of today."""
    state = {"today": date(2026, 10, 1)}
    monkeypatch.setattr(fact_history, "today", lambda: state["today"])
    return state


async def _approve(c, h, sid, body):
    r = await c.post(f"/api/v1/students/{sid}/lifecycle-events", headers=h, json=body)
    assert r.status_code == 201, r.text
    r = await c.post(f"/api/v1/lifecycle-events/{r.json()['id']}/approve", headers=h, json={})
    assert r.status_code == 200, r.text
    return r.json()


async def _history(c, h, sid, superseded=False):
    url = f"/api/v1/students/{sid}/status-history" + ("?includeSuperseded=true" if superseded else "")
    r = await c.get(url, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


async def _status(c, h, sid):
    return (await c.get(f"/api/v1/students/{sid}", headers=h)).json()["status"]


def _spans(rows):
    return [(r["status"], r["validFrom"], r["validTo"]) for r in rows]


# --------------------------------------------------------------------------------------
# Lifecycle events write dated history
# --------------------------------------------------------------------------------------

async def test_enrolment_opens_history(ctx, clock):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    r = await c.post("/api/v1/students/enrol", headers=h, json={
        "person": {"givenName": "Ana", "familyName": "Lee"},
        "programmeId": ids["programme"], "startDate": "2026-02-01",
    })
    assert r.status_code == 201, r.text
    rows = await _history(c, h, r.json()["id"])
    assert _spans(rows) == [("registered", "2026-02-01", None)]
    assert rows[0]["origin"] == "initial"


async def test_suspension_return_restores_writing_up(ctx, clock):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    sid = ids["student"]
    await _approve(c, h, sid, {"eventType": "writing_up", "reason": "Research complete",
                               "startDate": "2026-03-01"})
    assert await _status(c, h, sid) == "writing_up"

    await _approve(c, h, sid, {"eventType": "suspension", "reason": "Medical",
                               "startDate": "2026-05-01", "endDate": "2026-07-01"})
    assert await _status(c, h, sid) == "suspended"

    r = await c.post(f"/api/v1/students/{sid}/return", headers=h, json={"returnedOn": "2026-06-15"})
    assert r.status_code == 200, r.text
    # Back to writing up — the status before the suspension — not "active".
    assert await _status(c, h, sid) == "writing_up"
    assert _spans(await _history(c, h, sid)) == [
        ("active", "2026-01-01", "2026-03-01"),
        ("writing_up", "2026-03-01", "2026-05-01"),
        ("suspended", "2026-05-01", "2026-06-15"),
        ("writing_up", "2026-06-15", None),
    ]


async def test_future_suspension_waits_for_its_date(ctx, clock, monkeypatch):
    c, token, ids, sm = ctx
    h = await token("a@t.com")
    sid = ids["student"]
    clock["today"] = date(2026, 3, 1)
    await _approve(c, h, sid, {"eventType": "suspension", "reason": "Fieldwork break",
                               "startDate": "2026-04-01", "endDate": "2026-06-01"})
    # Approved, recorded, but not yet in force.
    assert await _status(c, h, sid) == "active"
    assert _spans(await _history(c, h, sid))[-1] == ("suspended", "2026-04-01", None)

    clock["today"] = date(2026, 4, 2)
    async with sm() as s:
        assert await StatusHistoryService(s).refresh_due() == 1
        await s.commit()
    assert await _status(c, h, sid) == "suspended"
    async with sm() as s:   # idempotent
        assert await StatusHistoryService(s).refresh_due() == 0


async def test_withdrawal_and_termination(ctx, clock):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    sid = ids["student"]
    await _approve(c, h, sid, {"eventType": "withdrawal", "reason": "Personal reasons",
                               "startDate": "2026-08-15"})
    assert await _status(c, h, sid) == "withdrawn"
    assert _spans(await _history(c, h, sid))[-1] == ("withdrawn", "2026-08-15", None)

    # Already left: no further lifecycle status change.
    r = await c.post(f"/api/v1/students/{sid}/lifecycle-events", headers=h, json={
        "eventType": "termination", "reason": "x", "startDate": "2026-09-01"})
    assert r.status_code == 422, r.text


async def test_effective_date_before_start_is_refused(ctx, clock):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    r = await c.post(f"/api/v1/students/{ids['student']}/lifecycle-events", headers=h, json={
        "eventType": "withdrawal", "reason": "x", "startDate": "2025-12-01"})
    assert r.status_code == 422, r.text


async def test_status_mode_programme_not_directly_editable(ctx, clock):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    sid = ids["student"]
    for body in ({"status": "withdrawn"}, {"studyMode": "part_time"}):
        r = await c.patch(f"/api/v1/students/{sid}", headers=h, json=body)
        assert r.status_code == 409, r.text
    # Undated fields still edit normally.
    r = await c.patch(f"/api/v1/students/{sid}", headers=h, json={"expectedEndDate": "2029-06-01"})
    assert r.status_code == 200, r.text
    assert await _status(c, h, sid) == "active"


# --------------------------------------------------------------------------------------
# Corrections
# --------------------------------------------------------------------------------------

async def test_correction_moves_boundary_and_keeps_audit(ctx, clock):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    sid = ids["student"]
    await _approve(c, h, sid, {"eventType": "suspension", "reason": "Medical",
                               "startDate": "2026-05-01", "endDate": "2026-07-01"})
    await c.post(f"/api/v1/students/{sid}/return", headers=h, json={"returnedOn": "2026-07-01"})
    rows = await _history(c, h, sid)
    suspended = next(r for r in rows if r["status"] == "suspended")

    # Someone without the elevated permission can't rewrite history.
    oh = await token("o@t.com")
    r = await c.post(f"/api/v1/students/{sid}/status-history/{suspended['id']}/correct",
                     headers=oh, json={"validFrom": "2026-05-08", "reason": "Wrong start entered"})
    assert r.status_code == 403, r.text

    r = await c.post(f"/api/v1/students/{sid}/status-history/{suspended['id']}/correct",
                     headers=h, json={"validFrom": "2026-05-08", "reason": "Wrong start entered"})
    assert r.status_code == 200, r.text
    assert r.json()["row"]["origin"] == "correction"

    assert _spans(await _history(c, h, sid)) == [
        ("active", "2026-01-01", "2026-05-08"),
        ("suspended", "2026-05-08", "2026-07-01"),
        ("active", "2026-07-01", None),
    ]
    everything = await _history(c, h, sid, superseded=True)
    assert len([r for r in everything if r["supersededBy"]]) == 2   # the wrong rows are kept

    # A correction needs a reason.
    live = await _history(c, h, sid)
    r = await c.post(f"/api/v1/students/{sid}/status-history/{live[1]['id']}/correct",
                     headers=h, json={"status": "on_leave", "reason": "  "})
    assert r.status_code == 422, r.text


async def test_correcting_a_superseded_row_is_refused(ctx, clock):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    sid = ids["student"]
    await _approve(c, h, sid, {"eventType": "writing_up", "reason": "x", "startDate": "2026-03-01"})
    row = (await _history(c, h, sid))[-1]
    r = await c.post(f"/api/v1/students/{sid}/status-history/{row['id']}/correct",
                     headers=h, json={"validFrom": "2026-03-10", "reason": "Wrong date"})
    assert r.status_code == 200, r.text
    r = await c.post(f"/api/v1/students/{sid}/status-history/{row['id']}/correct",
                     headers=h, json={"validFrom": "2026-03-12", "reason": "Again"})
    assert r.status_code == 409, r.text


# --------------------------------------------------------------------------------------
# The change algorithm, directly
# --------------------------------------------------------------------------------------

async def test_same_day_change_replaces_the_period(ctx, clock):
    _, _, ids, sm = ctx
    async with sm() as s:
        st = await s.get(Student, uuid.UUID(ids["student"]))
        hist = StatusHistoryService(s)
        d = date(2026, 4, 1)
        await hist.change(st, StudentStatus.writing_up, effective_from=d)
        await hist.change(st, StudentStatus.on_leave, effective_from=d)
        live = await hist.live_rows(st.id)
        assert [(r.status, r.valid_from, r.valid_to) for r in live] == [
            (StudentStatus.active, START, d), (StudentStatus.on_leave, d, None)]
        superseded = [r for r in await hist.all_rows(st.id) if r.superseded_by]
        assert [r.status for r in superseded] == [StudentStatus.writing_up]


async def test_backdated_change_stops_at_the_next_recorded_change(ctx, clock):
    _, _, ids, sm = ctx
    async with sm() as s:
        st = await s.get(Student, uuid.UUID(ids["student"]))
        hist = StatusHistoryService(s)
        await hist.change(st, StudentStatus.withdrawn, effective_from=date(2026, 8, 1))
        await hist.change(st, StudentStatus.writing_up, effective_from=date(2026, 5, 1))
        live = await hist.live_rows(st.id)
        assert [(r.status, r.valid_from, r.valid_to) for r in live] == [
            (StudentStatus.active, START, date(2026, 5, 1)),
            (StudentStatus.writing_up, date(2026, 5, 1), date(2026, 8, 1)),
            (StudentStatus.withdrawn, date(2026, 8, 1), None),
        ]
        # A bounded change may not run over the later recorded change.
        with pytest.raises(WorkflowError):
            await hist.change(st, StudentStatus.on_leave, effective_from=date(2026, 6, 1),
                              effective_to=date(2026, 9, 1))


async def test_bounded_change_resumes_the_earlier_value(ctx, clock):
    _, _, ids, sm = ctx
    async with sm() as s:
        st = await s.get(Student, uuid.UUID(ids["student"]))
        hist = StatusHistoryService(s)
        await hist.change(st, StudentStatus.on_leave, effective_from=date(2026, 3, 1),
                          effective_to=date(2026, 3, 15))
        live = await hist.live_rows(st.id)
        assert [(r.status, r.valid_from, r.valid_to) for r in live] == [
            (StudentStatus.active, START, date(2026, 3, 1)),
            (StudentStatus.on_leave, date(2026, 3, 1), date(2026, 3, 15)),
            (StudentStatus.active, date(2026, 3, 15), None),
        ]
        assert st.status is StudentStatus.active   # today (Oct) is back to active


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6])
async def test_random_changes_keep_the_invariants(ctx, clock, seed):
    """Seeded random sequences of changes and corrections. Whatever is accepted, the live
    timeline stays contiguous and non-overlapping, and the cache matches today."""
    _, _, ids, sm = ctx
    rnd = random.Random(seed)
    statuses = [StudentStatus.active, StudentStatus.writing_up, StudentStatus.suspended,
                StudentStatus.on_leave, StudentStatus.withdrawn]
    async with sm() as s:
        st = await s.get(Student, uuid.UUID(ids["student"]))
        hist = StatusHistoryService(s)
        await hist.initialise(st)
        accepted = 0
        for _ in range(40):
            clock["today"] = START + timedelta(days=rnd.randint(0, 600))
            day = START + timedelta(days=rnd.randint(0, 600))
            try:
                if rnd.random() < 0.75:
                    to = day + timedelta(days=rnd.randint(1, 90)) if rnd.random() < 0.3 else None
                    await hist.change(st, rnd.choice(statuses), effective_from=day, effective_to=to)
                else:
                    live = await hist.live_rows(st.id)
                    row = rnd.choice(live)
                    await hist.correct(row.id, valid_from=day if rnd.random() < 0.6 else None,
                                       status=rnd.choice(statuses), reason="random")
                accepted += 1
            except WorkflowError:
                pass   # a refused operation is fine; it must just not break anything
            live = await hist.live_rows(st.id)
            StatusHistoryService.assert_valid(live)
            await hist.refresh_cache(st)
            cover = await hist.value_at(st.id, clock["today"])
            if cover is not None:
                assert st.status == cover.status
        assert accepted > 10


# --------------------------------------------------------------------------------------
# Backfill
# --------------------------------------------------------------------------------------

def test_build_timeline_pure():
    t = date(2026, 10, 1)
    # Closed suspension, then current status runs on.
    assert build_timeline(status="active", start=START, graduation_date=None, today=t,
                          suspensions=[("e1", date(2026, 3, 1), date(2026, 5, 1))]) == [
        (START, date(2026, 3, 1), "active", None),
        (date(2026, 3, 1), date(2026, 5, 1), "suspended", "e1"),
        (date(2026, 5, 1), None, "active", None),
    ]
    # Completed with a graduation date.
    assert build_timeline(status="completed", start=START, graduation_date=date(2026, 7, 1),
                          today=t, suspensions=[]) == [
        (START, date(2026, 7, 1), "active", None),
        (date(2026, 7, 1), None, "completed", None),
    ]
    # Cache disagrees with the rebuilt timeline today: the cache wins from today.
    assert build_timeline(status="suspended", start=START, graduation_date=None, today=t,
                          suspensions=[("e2", date(2026, 12, 1), None)]) == [
        (START, t, "active", None),
        (t, None, "suspended", None),
    ]


async def test_backfill_agrees_with_cache(ctx):
    _, _, ids, sm = ctx
    async with sm() as s:
        st = await s.get(Student, uuid.UUID(ids["student"]))
        st.status = StudentStatus.suspended
        s.add(StudentLifecycleEvent(
            student_id=st.id, event_type=LifecycleEventType.suspension,
            status=LifecycleEventStatus.approved, start_date=date(2026, 6, 1),
            end_date=date(2026, 12, 1), reason="Medical",
        ))
        await s.commit()
    eng = sm.kw["bind"]
    async with eng.begin() as conn:
        result = await conn.run_sync(lambda c: backfill_status_history(c, today=date(2026, 10, 1)))
        assert result["students"] == 1
        assert await conn.run_sync(lambda c: check_status_history(c, today=date(2026, 10, 1))) == []
        again = await conn.run_sync(lambda c: backfill_status_history(c, today=date(2026, 10, 1)))
        assert again["students"] == 0   # idempotent
    async with sm() as s:
        rows = (await s.execute(select(StudentStatusHistory).order_by(StudentStatusHistory.valid_from))).scalars().all()
        assert [(r.status, r.valid_from, r.valid_to, r.origin) for r in rows] == [
            (StudentStatus.active, START, date(2026, 6, 1), "backfill"),
            (StudentStatus.suspended, date(2026, 6, 1), None, "backfill"),
        ]
