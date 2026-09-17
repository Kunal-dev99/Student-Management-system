"""Mid-term programme transfer (MPhil -> PhD, PhD -> MSc, ...).

Rides the shared request -> approve -> recalculate pipeline the other lifecycle events use, so
what has to hold is:

- requesting alone changes nothing (student.programme_id stays put)
- approval swaps the current programme, cancels undecided milestones, generates the new schedule
- decided milestones remain historical facts
- ``original_expected_end_date`` is preserved (baseline immutability) even when the new programme
  moves ``expected_end_date`` forward or back
- cross-type transfers (research <-> taught) are ALLOWED with warnings, not blocked
- HESA ``build_records`` slices a mid-year transfer into one record per period, with the correct
  programme code on each
- ``student.write`` is required to request; ``student.lifecycle.approve`` is required to approve
"""
from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone, MilestoneDefinition
from app.modules.student_record.constants import ProgrammeType, StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student

START = date(2026, 10, 1)   # Autumn 2026, inside the 2026/27 UK academic year window
ORIGINAL_END = date(2029, 10, 1)


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    ids: dict = {}
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        pgr_admin = Role(name="PGR Administrator"); s.add(pgr_admin); await s.flush()
        await s.refresh(pgr_admin, ["permissions"]); pgr_admin.permissions = list(perms.values())
        user = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"])
        user.roles = [role, pgr_admin]

        # A read-only user proves the write endpoint refuses unauthorised requests.
        ro_role = Role(name="ReadOnly"); s.add(ro_role); await s.flush()
        await s.refresh(ro_role, ["permissions"])
        ro_role.permissions = [perms["student.read"]]
        ro_user = User(email="ro@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(ro_user); await s.flush(); await s.refresh(ro_user, ["roles"])
        ro_user.roles = [ro_role]

        # Two research programmes (MPhil, PhD) and one taught (MSc) for the cross-type test.
        mphil = Programme(name="MPhil Physics", code="MPHIL",
                          programme_type=ProgrammeType.research, duration_months=24)
        phd = Programme(name="PhD Physics", code="PHD",
                        programme_type=ProgrammeType.research, duration_months=36)
        msc = Programme(name="MSc Physics", code="MSC",
                        programme_type=ProgrammeType.taught, duration_months=12,
                        taught_total_credits=180)
        s.add_all([mphil, phd, msc]); await s.flush()
        ids["mphil"] = str(mphil.id); ids["phd"] = str(phd.id); ids["msc"] = str(msc.id)

        # Milestone definitions per programme — the PhD schedule should be generated on approval,
        # and the MPhil's undecided milestones cancelled.
        s.add_all([
            MilestoneDefinition(programme_id=mphil.id, name="MPhil Confirmation", due_offset_days=180),
            MilestoneDefinition(programme_id=phd.id, name="PhD Confirmation", due_offset_days=270),
            MilestoneDefinition(programme_id=phd.id, name="PhD Annual Review 1", due_offset_days=365),
            MilestoneDefinition(programme_id=msc.id, name="MSc Dissertation Proposal", due_offset_days=60),
        ])
        await s.flush()

        person = Person(given_name="Nina", family_name="Patel"); s.add(person); await s.flush()
        student = Student(
            person_id=person.id, student_ref="PGR-PT", programme_id=mphil.id,
            start_date=START, expected_end_date=ORIGINAL_END,
            original_expected_end_date=ORIGINAL_END,
            study_mode=StudyMode.full_time, status=StudentStatus.active,
        )
        s.add(student); await s.flush()
        ids["student"] = str(student.id)

        # An undecided (superseded) and a decided (historical fact) milestone on the MPhil.
        from sqlalchemy import select as _sel
        mphil_defn = (await s.execute(
            _sel(MilestoneDefinition).where(MilestoneDefinition.programme_id == mphil.id)
        )).scalars().first()
        undecided = Milestone(
            student_id=student.id,
            milestone_definition_id=mphil_defn.id,
            due_date=date(2027, 4, 1), status=MilestoneStatus.due, name="MPhil Confirmation",
        )
        decided = Milestone(
            student_id=student.id, milestone_definition_id=None,
            due_date=date(2026, 12, 1), status=MilestoneStatus.decided, name="Induction",
        )
        s.add_all([undecided, decided]); await s.flush()
        ids["undecided"] = str(undecided.id)
        ids["decided"] = str(decided.id)
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        async def token(email):
            r = await c.post("/api/v1/auth/login", json={"email": email, "password": "pw"})
            return {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, token, ids, sm
    app.dependency_overrides.clear()
    await eng.dispose()


async def _request(c, h, sid, new_prog_id, effective="2027-02-01", reason="Upgrade to PhD after successful review"):
    return await c.post(f"/api/v1/students/{sid}/lifecycle-events", headers=h, json={
        "eventType": "programme_change",
        "reason": reason,
        "startDate": effective,
        "newProgrammeId": new_prog_id,
    })


# --------------------------------------------------------------------------------------
# Happy path: same-type upgrade MPhil -> PhD
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_alone_leaves_the_student_unchanged(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    r = await _request(c, h, ids["student"], ids["phd"])
    assert r.status_code == 201, r.text
    event = r.json()
    assert event["status"] == "requested"
    assert event["newProgrammeId"] == ids["phd"]
    assert event["effectiveDate"] == "2027-02-01"

    student = (await c.get(f"/api/v1/students/{ids['student']}", headers=h)).json()
    assert student["programmeId"] == ids["mphil"]         # not swapped yet


@pytest.mark.asyncio
async def test_approval_swaps_programme_and_rebuilds_milestone_schedule(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    ev = (await _request(c, h, ids["student"], ids["phd"])).json()
    result = (await c.post(f"/api/v1/lifecycle-events/{ev['id']}/approve", headers=h, json={})).json()

    recalc = result["recalculation"]
    assert recalc["newProgrammeId"] == ids["phd"]
    assert recalc["previousProgrammeCode"] == "MPHIL"
    assert recalc["newProgrammeCode"] == "PHD"
    assert recalc["crossType"] is False
    assert recalc["milestonesCancelled"] == 1             # only the undecided one
    assert recalc["milestonesGenerated"] == 2             # both PhD definitions instantiated
    assert result.get("warnings"), "expected carry-over warning for supervisors and funding"

    student = (await c.get(f"/api/v1/students/{ids['student']}", headers=h)).json()
    assert student["programmeId"] == ids["phd"]
    # Baseline preserved even though expected_end_date has been recomputed.
    assert student["originalExpectedEndDate"] == ORIGINAL_END.isoformat()
    # New end = effective + PhD duration (36 months) = 2027-02-01 + 36m = 2030-02-01.
    assert student["expectedEndDate"] == "2030-02-01"

    milestones = (await c.get(f"/api/v1/students/{ids['student']}/milestones", headers=h)).json()
    by_id = {m["id"]: m for m in milestones}
    assert by_id[ids["undecided"]]["status"] == "cancelled"
    assert "superseded by programme change to PHD" in by_id[ids["undecided"]]["name"]
    assert by_id[ids["decided"]]["status"] == "decided"    # historical fact left alone

    # The PhD milestones are anchored on the effective date, not on the student's start.
    phd_names = {m["name"] for m in milestones if m["status"] != "cancelled" and m["id"] != ids["decided"]}
    assert phd_names == {"PhD Confirmation", "PhD Annual Review 1"}


# --------------------------------------------------------------------------------------
# Cross-type transfer: PhD -> MSc (research -> taught)
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_type_transfer_is_allowed_and_warns(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    # Move onto the PhD first so we can then downgrade to a taught MSc.
    ev = (await _request(c, h, ids["student"], ids["phd"])).json()
    await c.post(f"/api/v1/lifecycle-events/{ev['id']}/approve", headers=h, json={})

    ev2 = (await c.post(f"/api/v1/students/{ids['student']}/lifecycle-events", headers=h, json={
        "eventType": "programme_change",
        "reason": "Downgrade to MSc after further review",
        "startDate": "2027-06-01",
        "newProgrammeId": ids["msc"],
    })).json()
    result = (await c.post(f"/api/v1/lifecycle-events/{ev2['id']}/approve", headers=h, json={})).json()

    assert result["crossType"] is True
    warnings = result.get("warnings") or []
    joined = " ".join(warnings).lower()
    assert "cross-type" in joined
    assert "research" in joined and "taught" in joined
    # Supervisors and funding are student-scoped — the warning must call the carry-over out.
    assert "supervisor" in joined or "funding" in joined

    student = (await c.get(f"/api/v1/students/{ids['student']}", headers=h)).json()
    assert student["programmeId"] == ids["msc"]


# --------------------------------------------------------------------------------------
# HESA per-period slicing
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_records_slices_a_mid_year_transfer_into_two_periods(ctx):
    c, token, ids, sm = ctx
    h = await token("a@t.com")
    # Effective 1 Feb 2027 sits inside the 2026/27 UK academic year (1 Aug 2026 - 31 Jul 2027),
    # so the return should emit one MPhil row (start -> 2027-01-31) and one PhD row (2027-02-01
    # -> year end) for this student.
    ev = (await _request(c, h, ids["student"], ids["phd"], effective="2027-02-01")).json()
    await c.post(f"/api/v1/lifecycle-events/{ev['id']}/approve", headers=h, json={})

    from app.modules.exports.statutory import StatutoryEngine

    async with sm() as session:
        engine = StatutoryEngine(session)
        # No academic_year -> single record per student (backwards compat).
        flat = await engine.build_records()
        assert len(flat) == 1

        # With academic_year -> per-period slicing kicks in.
        sliced = await engine.build_records(academic_year="2026/27")
        codes = [r["programme"]["code"] for r in sliced]
        assert sorted(codes) == ["MPHIL", "PHD"]
        assert len(sliced) == 2
        # HUSID stays stable for the person (the student didn't change, just the programme).
        husids = {r["student"]["husid"] for r in sliced}
        assert len(husids) == 1
        # Each row's period-anchored start / end date should differ.
        starts = {r["student"]["startDate"] for r in sliced}
        assert len(starts) == 2

    # A window with no fan-out (only one programme in force during it) keeps the historical
    # single-record shape, using the student's current programme pointer.
    async with sm() as session:
        pre = await StatutoryEngine(session).build_records(academic_year="2025/26")
        assert len(pre) == 1


# --------------------------------------------------------------------------------------
# Authorisation
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_only_user_cannot_request_a_programme_change(ctx):
    c, token, ids, _ = ctx
    h_ro = await token("ro@t.com")
    r = await _request(c, h_ro, ids["student"], ids["phd"])
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_requesting_a_change_to_the_same_programme_is_refused(ctx):
    c, token, ids, _ = ctx
    h = await token("a@t.com")
    r = await _request(c, h, ids["student"], ids["mphil"])
    assert r.status_code == 422
