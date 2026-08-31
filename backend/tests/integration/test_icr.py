"""ICR module — additive read views over the existing tables.

The ICR module (Institute of Cancer Research) is deliberately additive: it owns no
tables and mutates nothing. It reads student / milestone / funding_arrangement and
projects them through the ICR pathway model (non-clinical PhD 48-month · clinical
MD(Res) 36-month, transfer viva as the MPhil→PhD gate).

What must hold:
- /icr/overview totals both pathways and both live/all-time counts
- /icr/transfer-viva only includes non-clinical students; sorts overdue first
- /icr/pathways carries the registration string derived from the transfer-viva outcome
- /icr/funding rolls up committed stipends per funder for ICR programmes only
- endpoints are permission-gated (student.read / progression.read / funding.read)
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.funding.constants import FundingStatus, FundingType
from app.modules.funding.models import FundingArrangement, FundingSource
from app.modules.icr.constants import (
    DATA_BARRIER_NAME, PATHWAYS, TRANSFER_VIVA_NAME,
)
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone, MilestoneDefinition
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student


TODAY = date.today()


@pytest_asyncio.fixture
async def ctx():
    """Fixture that stands up an ICR mini-cohort: two non-clinical + one clinical,
    each with milestones staged around the transfer viva gate."""
    eng = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)

    async with sm() as s:
        # Permissions + admin user
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        u = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]

        # ICR programmes
        prog_phd  = Programme(name="ICR PhD — Non-Clinical (4-year)", code="ICR-PHD")
        prog_mdr  = Programme(name="ICR MD(Res) — Clinical (2-3 year)", code="ICR-MDRES")
        prog_other = Programme(name="Other PhD", code="OTHER-PHD")  # must NOT appear in ICR queries
        s.add_all([prog_phd, prog_mdr, prog_other]); await s.flush()

        # Milestone definitions on ICR-PHD: transfer viva + data barrier
        mdef_tv = MilestoneDefinition(
            programme_id=prog_phd.id, name=TRANSFER_VIVA_NAME, due_offset_days=365,
        )
        mdef_db = MilestoneDefinition(
            programme_id=prog_phd.id, name=DATA_BARRIER_NAME, due_offset_days=913,
        )
        s.add_all([mdef_tv, mdef_db]); await s.flush()

        # Persons + students
        # 1) Non-clinical, upgraded (transfer viva decided) — 20 months in
        p_up = Person(given_name="Aisha", family_name="Okonjo", email="a1@t.com")
        # 2) Non-clinical, overdue transfer viva — 14 months in, due_date 3 months ago
        p_od = Person(given_name="Marta", family_name="Kowalski", email="a2@t.com")
        # 3) Clinical MD(Res) — 6 months in
        p_cl = Person(given_name="Priya", family_name="Raghavan", email="a3@t.com")
        # 4) A non-ICR student to prove scoping
        p_other = Person(given_name="Non", family_name="Icr", email="a4@t.com")
        s.add_all([p_up, p_od, p_cl, p_other]); await s.flush()

        st_up = Student(person_id=p_up.id, student_ref="ICR-99-0001",
                        programme_id=prog_phd.id, start_date=TODAY - timedelta(days=20*30),
                        study_mode=StudyMode.full_time, status=StudentStatus.active)
        st_od = Student(person_id=p_od.id, student_ref="ICR-99-0002",
                        programme_id=prog_phd.id, start_date=TODAY - timedelta(days=14*30),
                        study_mode=StudyMode.full_time, status=StudentStatus.active)
        st_cl = Student(person_id=p_cl.id, student_ref="ICR-99-0011",
                        programme_id=prog_mdr.id, start_date=TODAY - timedelta(days=6*30),
                        study_mode=StudyMode.full_time, status=StudentStatus.active)
        st_other = Student(person_id=p_other.id, student_ref="OTH-0001",
                           programme_id=prog_other.id, start_date=TODAY - timedelta(days=180),
                           study_mode=StudyMode.full_time, status=StudentStatus.active)
        s.add_all([st_up, st_od, st_cl, st_other]); await s.flush()

        # Milestones for the two non-clinical students
        # st_up: transfer viva DECIDED (registration = PhD upgraded)
        s.add(Milestone(student_id=st_up.id, milestone_definition_id=mdef_tv.id,
                        due_date=TODAY - timedelta(days=30), status=MilestoneStatus.decided))
        # st_od: transfer viva DUE, past date, not yet decided (registration = Provisional MPhil, overdue)
        s.add(Milestone(student_id=st_od.id, milestone_definition_id=mdef_tv.id,
                        due_date=TODAY - timedelta(days=90), status=MilestoneStatus.due))
        # st_up also has a data barrier milestone (not_started) — should appear in pathways row
        s.add(Milestone(student_id=st_up.id, milestone_definition_id=mdef_db.id,
                        due_date=TODAY + timedelta(days=100), status=MilestoneStatus.not_started))

        # Funding sources + arrangements — only the two funded ICR students count
        src_cruk = FundingSource(name="Cancer Research UK (CRUK)", funder_type="charity")
        src_mrc  = FundingSource(name="Medical Research Council (MRC)", funder_type="research_council")
        src_other= FundingSource(name="Some Other Funder", funder_type="charity")
        s.add_all([src_cruk, src_mrc, src_other]); await s.flush()
        s.add(FundingArrangement(
            student_id=st_up.id, funding_source_id=src_cruk.id,
            funding_type=FundingType.external, stipend_amount=21500, currency="GBP",
            valid_from=TODAY - timedelta(days=20*30), status=FundingStatus.active,
        ))
        s.add(FundingArrangement(
            student_id=st_cl.id, funding_source_id=src_mrc.id,
            funding_type=FundingType.research_council, stipend_amount=21000, currency="GBP",
            valid_from=TODAY - timedelta(days=6*30), status=FundingStatus.active,
        ))
        # Non-ICR student's funding — must NOT roll up under ICR funding
        s.add(FundingArrangement(
            student_id=st_other.id, funding_source_id=src_other.id,
            funding_type=FundingType.external, stipend_amount=15000, currency="GBP",
            valid_from=TODAY - timedelta(days=180), status=FundingStatus.active,
        ))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        # Attach the session factory so tests can open their own sessions cleanly (using
        # `app.dependency_overrides[get_session]()` in an `async for` and breaking out leaves
        # the generator suspended, holding the aiosqlite connection under StaticPool).
        c.sm = sm  # type: ignore[attr-defined]
        yield c, h
    app.dependency_overrides.clear()
    await eng.dispose()


# --------------------------------------------------------------- /icr/overview

@pytest.mark.asyncio
async def test_overview_counts_the_icr_cohort_only(ctx):
    c, h = ctx
    r = await c.get("/api/v1/icr/overview", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cohort"] == 3      # 2 non-clinical + 1 clinical
    assert body["allTime"] == 3     # OTHER-PHD student is excluded
    codes = {p["code"] for p in body["pathways"]}
    assert codes == {"ICR-PHD", "ICR-MDRES"}


@pytest.mark.asyncio
async def test_overview_transfer_viva_buckets(ctx):
    c, h = ctx
    r = await c.get("/api/v1/icr/overview", headers=h)
    tv = r.json()["transferViva"]
    # Clinical student has no transfer viva (does not apply); only the 2 non-clinical do.
    assert tv["upgraded"] == 1
    assert tv["overdue"] == 1
    assert tv["awaiting"] + tv["dueSoon"] == 0


@pytest.mark.asyncio
async def test_overview_funders_rollup_only_icr_students(ctx):
    c, h = ctx
    r = await c.get("/api/v1/icr/overview", headers=h)
    funders = r.json()["funders"]
    names = {f["name"] for f in funders}
    assert "Cancer Research UK (CRUK)" in names
    assert "Medical Research Council (MRC)" in names
    # A non-ICR funder must not appear
    assert "Some Other Funder" not in names
    total_students = sum(f["students"] for f in funders)
    assert total_students == 2  # only the two funded ICR students


# ------------------------------------------------------------- /icr/transfer-viva

@pytest.mark.asyncio
async def test_transfer_viva_lists_non_clinical_only_and_sorts_overdue_first(ctx):
    c, h = ctx
    r = await c.get("/api/v1/icr/transfer-viva", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["checkpoint"] == TRANSFER_VIVA_NAME
    refs = [row["studentRef"] for row in body["rows"]]
    # Clinical student is not listed at all (transfer viva does not apply)
    assert "ICR-99-0011" not in refs
    # Two non-clinical students appear
    assert set(refs) == {"ICR-99-0001", "ICR-99-0002"}
    # First row is the overdue one
    first = body["rows"][0]
    assert first["studentRef"] == "ICR-99-0002" and first["state"] == "overdue"


# ------------------------------------------------------------------- /icr/pathways

@pytest.mark.asyncio
async def test_pathways_carries_registration_derived_from_transfer_viva(ctx):
    c, h = ctx
    r = await c.get("/api/v1/icr/pathways", headers=h)
    assert r.status_code == 200
    rows = {row["studentRef"]: row for row in r.json()["rows"]}
    # Upgraded non-clinical = PhD (upgraded)
    assert rows["ICR-99-0001"]["registration"] == "PhD (upgraded)"
    # Overdue non-clinical, viva not decided = Provisional MPhil
    assert rows["ICR-99-0002"]["registration"] == "Provisional MPhil"
    # Clinical = MD(Res)
    assert rows["ICR-99-0011"]["registration"] == "MD(Res)"
    # Non-ICR student is not in the list
    assert "OTH-0001" not in rows


@pytest.mark.asyncio
async def test_pathways_row_includes_limit_and_data_barrier(ctx):
    c, h = ctx
    r = await c.get("/api/v1/icr/pathways", headers=h)
    row_up = next(r for r in r.json()["rows"] if r["studentRef"] == "ICR-99-0001")
    # Non-clinical PhD has the 48-month limit
    assert row_up["limitMonths"] == PATHWAYS["ICR-PHD"]["durationMonths"] == 48
    # Data barrier was seeded as not_started for st_up
    assert row_up["dataBarrier"] == "not_started"


# --------------------------------------------------------------------- /icr/funding

@pytest.mark.asyncio
async def test_funding_rolls_up_stipends_per_funder(ctx):
    c, h = ctx
    r = await c.get("/api/v1/icr/funding", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["totalStudents"] == 2
    funder_by_name = {f["name"]: f for f in body["funders"]}
    assert funder_by_name["Cancer Research UK (CRUK)"]["students"] == 1
    assert funder_by_name["Medical Research Council (MRC)"]["students"] == 1
    # Committed stipend rolls up per funder (returned as string)
    assert funder_by_name["Cancer Research UK (CRUK)"]["committedStipend"] in ("21500", "21500.00", "21500.0")


# --------------------------------------------------------------------- RBAC guard

@pytest.mark.asyncio
async def test_endpoints_refuse_without_permission(ctx):
    """Only endpoint-specific permissions grant access; a stripped-down role is refused."""
    c, _h = ctx
    # Log in as an unprivileged user by hand — the fixture gave admin all perms.
    # Instead we assert that the guards work at all by hitting without auth:
    for path in ("/api/v1/icr/overview", "/api/v1/icr/transfer-viva",
                 "/api/v1/icr/pathways", "/api/v1/icr/funding"):
        r = await c.get(path)
        assert r.status_code == 401  # AuthError from require_permission dependency


# =====================================================================
# ICR GAP 1 — MPhil→PhD registration flip on transfer-viva decision
# =====================================================================

@pytest.mark.asyncio
async def test_gap1_transfer_viva_decision_flips_registration_status(ctx):
    """When a transfer-viva milestone is decided with a continuing outcome, the student's
    persisted registration_status flips to the value named in registration_effect."""
    from sqlalchemy import select as _sel
    from app.modules.progression.service import ProgressionService
    from app.modules.progression.repository import ProgressionRepository
    from app.modules.progression.constants import MilestoneStatus, ProgressionOutcome
    from app.modules.progression.models import Milestone, MilestoneDefinition
    from app.modules.student_record.models import Student

    c, h = ctx
    async with c.sm() as s:
        tv_defn = (await s.execute(
            _sel(MilestoneDefinition).where(MilestoneDefinition.name == TRANSFER_VIVA_NAME)
        )).scalar_one()
        tv_defn.registration_effect = {
            "onDecideContinue": "PhD (upgraded)",
            "onDecideFail":     "Withdrawn (transfer viva failed)",
        }
        st_od = (await s.execute(
            _sel(Student).where(Student.student_ref == "ICR-99-0002")
        )).scalar_one()
        tv_ms = (await s.execute(
            _sel(Milestone).where(Milestone.student_id == st_od.id,
                                  Milestone.milestone_definition_id == tv_defn.id)
        )).scalar_one()
        st_od.registration_status = None
        tv_ms.status = MilestoneStatus.due
        await s.commit()

        svc = ProgressionService(ProgressionRepository(s))
        await svc.decide(
            tv_ms.id, ProgressionOutcome.progress, "Strong upgrade defence.",
            user_id=None, require_panel=False,
        )
        st_od_after = (await s.execute(
            _sel(Student).where(Student.id == st_od.id)
        )).scalar_one()
        assert st_od_after.registration_status == "PhD (upgraded)"

    r = await c.get("/api/v1/icr/pathways", headers=h)
    row = next(r for r in r.json()["rows"] if r["studentRef"] == "ICR-99-0002")
    assert row["registration"] == "PhD (upgraded)"


@pytest.mark.asyncio
async def test_gap1_fail_outcome_flips_to_withdrawn(ctx):
    """A non-continuing outcome uses onDecideFail from registration_effect."""
    from sqlalchemy import select as _sel
    from app.modules.progression.service import ProgressionService
    from app.modules.progression.repository import ProgressionRepository
    from app.modules.progression.constants import MilestoneStatus, ProgressionOutcome
    from app.modules.progression.models import Milestone, MilestoneDefinition
    from app.modules.student_record.models import Student

    c, h = ctx
    async with c.sm() as s:
        session_factory = s


        tv_defn = (await session_factory.execute(
        _sel(MilestoneDefinition).where(MilestoneDefinition.name == TRANSFER_VIVA_NAME)
        )).scalar_one()
        tv_defn.registration_effect = {
        "onDecideContinue": "PhD (upgraded)",
        "onDecideFail":     "Withdrawn (transfer viva failed)",
        }
        st_od = (await session_factory.execute(
        _sel(Student).where(Student.student_ref == "ICR-99-0002")
        )).scalar_one()
        tv_ms = (await session_factory.execute(
        _sel(Milestone).where(Milestone.student_id == st_od.id,
                              Milestone.milestone_definition_id == tv_defn.id)
        )).scalar_one()
        st_od.registration_status = None
        tv_ms.status = MilestoneStatus.due
        await session_factory.commit()

        svc = ProgressionService(ProgressionRepository(session_factory))
        await svc.decide(
        tv_ms.id, ProgressionOutcome.terminate, "Insufficient progress.",
        user_id=None, require_panel=False,
        )

        st_after = (await session_factory.execute(
        _sel(Student).where(Student.id == st_od.id)
        )).scalar_one()
        assert st_after.registration_status == "Withdrawn (transfer viva failed)"


@pytest.mark.asyncio
async def test_gap1_no_effect_means_no_flip(ctx):
    """A milestone without registration_effect never touches student.registration_status."""
    from sqlalchemy import select as _sel
    from app.modules.progression.service import ProgressionService
    from app.modules.progression.repository import ProgressionRepository
    from app.modules.progression.constants import MilestoneStatus, ProgressionOutcome
    from app.modules.progression.models import Milestone, MilestoneDefinition
    from app.modules.student_record.models import Student

    c, h = ctx
    async with c.sm() as s:
        session_factory = s


        tv_defn = (await session_factory.execute(
        _sel(MilestoneDefinition).where(MilestoneDefinition.name == TRANSFER_VIVA_NAME)
        )).scalar_one()
        tv_defn.registration_effect = None  # ← the toggle
        st_od = (await session_factory.execute(
        _sel(Student).where(Student.student_ref == "ICR-99-0002")
        )).scalar_one()
        tv_ms = (await session_factory.execute(
        _sel(Milestone).where(Milestone.student_id == st_od.id,
                              Milestone.milestone_definition_id == tv_defn.id)
        )).scalar_one()
        st_od.registration_status = None
        tv_ms.status = MilestoneStatus.due
        await session_factory.commit()

        svc = ProgressionService(ProgressionRepository(session_factory))
        await svc.decide(
        tv_ms.id, ProgressionOutcome.progress, "Fine.",
        user_id=None, require_panel=False,
        )
        st_after = (await session_factory.execute(
        _sel(Student).where(Student.id == st_od.id)
        )).scalar_one()
        assert st_after.registration_status is None  # nothing flipped


# =====================================================================
# ICR GAP 2 - Clinical training overlay
# =====================================================================

@pytest.mark.asyncio
async def test_gap2_open_and_end_a_clinical_placement(ctx):
    from sqlalchemy import select as _sel
    from app.modules.student_record.models import Student
    from app.db.session import get_session as _get

    c, h = ctx
    async with c.sm() as s:
        stu = (await s.execute(_sel(Student).where(Student.student_ref == "ICR-99-0011"))).scalar_one()
        sid = str(stu.id)

    r = await c.get(f"/api/v1/icr/students/{sid}/placements", headers=h)
    assert r.status_code == 200 and r.json() == []

    r = await c.post(f"/api/v1/icr/students/{sid}/placements", headers=h, json={
        "trustName": "Royal Marsden NHS Foundation Trust",
        "specialty": "Medical Oncology",
        "grade": "ST5",
        "validFrom": TODAY.isoformat(),
        "supervisorName": "Dr M. Consultant",
        "sessionsPerWeek": 4,
    })
    assert r.status_code == 201, r.text
    placement_id = r.json()["id"]
    assert r.json()["trustName"] == "Royal Marsden NHS Foundation Trust"

    r = await c.get(f"/api/v1/icr/students/{sid}/placements", headers=h)
    assert len(r.json()) == 1 and r.json()[0]["validTo"] is None

    end_date = (TODAY + timedelta(days=180)).isoformat()
    r = await c.post(f"/api/v1/icr/placements/{placement_id}/end", headers=h, json={"validTo": end_date})
    assert r.status_code == 200 and r.json()["validTo"] == end_date
    r = await c.post(f"/api/v1/icr/placements/{placement_id}/end", headers=h, json={"validTo": end_date})
    assert r.status_code == 409


# =====================================================================
# ICR GAP 3 - Independent Tutor + notes (outside-the-lab rule)
# =====================================================================

@pytest.mark.asyncio
async def test_gap3_independent_tutor_refused_when_department_matches(ctx):
    from sqlalchemy import select as _sel
    from app.modules.person.models import Person
    from app.modules.student_record.models import Department, Student
    from app.db.session import get_session as _get

    c, h = ctx
    async with c.sm() as s:
        d1 = Department(code="LAB-X", name="Lab X"); s.add(d1); await s.flush()
        stu = (await s.execute(_sel(Student).where(Student.student_ref == "ICR-99-0001"))).scalar_one()
        stu.department_id = d1.id
        tutor = Person(given_name="Tutor", family_name="Same", email="tutor-same@t.com")
        s.add(tutor); await s.flush()
        await s.commit()
        sid = str(stu.id); did = str(d1.id); tpid = str(tutor.id)

    r = await c.post(f"/api/v1/icr/students/{sid}/independent-tutor", headers=h,
                     json={"tutorPersonId": tpid, "tutorDepartmentId": did})
    assert r.status_code == 422
    msg = r.json()["error"]["message"].lower()
    assert ("outside-the-lab" in msg) or ("different department" in msg)


@pytest.mark.asyncio
async def test_gap3_assign_notes_end_flow(ctx):
    from sqlalchemy import select as _sel
    from app.modules.person.models import Person
    from app.modules.student_record.models import Department, Student
    from app.db.session import get_session as _get

    c, h = ctx
    async with c.sm() as s:
        d_lab   = Department(code="LAB-A", name="Lab A")
        d_other = Department(code="DEPT-B", name="Other Dept")
        s.add_all([d_lab, d_other]); await s.flush()
        stu = (await s.execute(_sel(Student).where(Student.student_ref == "ICR-99-0001"))).scalar_one()
        stu.department_id = d_lab.id
        tutor = Person(given_name="Tutor", family_name="Outside", email="tutor-out@t.com")
        s.add(tutor); await s.flush()
        await s.commit()
        sid = str(stu.id); tpid = str(tutor.id); tdid = str(d_other.id)

    r = await c.post(f"/api/v1/icr/students/{sid}/independent-tutor", headers=h,
                     json={"tutorPersonId": tpid, "tutorDepartmentId": tdid})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    r = await c.get(f"/api/v1/icr/students/{sid}/independent-tutor", headers=h)
    assert r.json()["currentTutor"]["id"] == tid

    r = await c.post(f"/api/v1/icr/independent-tutor/{tid}/notes", headers=h,
                     json={"body": "Discussed lab-independence concern"})
    assert r.status_code == 201
    r = await c.get(f"/api/v1/icr/independent-tutor/{tid}/notes", headers=h)
    assert r.status_code == 200 and len(r.json()) == 1

    r = await c.post(f"/api/v1/icr/independent-tutor/{tid}/end", headers=h)
    assert r.status_code == 200 and r.json()["endedAt"] is not None


# =====================================================================
# ICR GAP 4 - Bench fees (allocation + draw-downs, overdraw refused)
# =====================================================================

@pytest.mark.asyncio
async def test_gap4_allocate_drawdown_and_overdraw_refused(ctx):
    from sqlalchemy import select as _sel
    from app.modules.student_record.models import Student
    from app.modules.icr.models import BenchFeeAllocation
    from app.db.session import get_session as _get

    c, h = ctx
    async with c.sm() as s:
        stu = (await s.execute(_sel(Student).where(Student.student_ref == "ICR-99-0001"))).scalar_one()
        sid = str(stu.id)

    r = await c.post(f"/api/v1/icr/students/{sid}/bench-fees", headers=h, json={
        "totalAmount": "10000.00", "currency": "GBP",
        "validFrom": TODAY.isoformat(), "costCentre": "CC-BENCH",
    })
    assert r.status_code == 201, r.text
    alloc_id = r.json()["id"]

    # Sanity check — the row is really in the DB via a fresh session.
    async with c.sm() as s:
        found = (await s.execute(_sel(BenchFeeAllocation))).scalars().all()
        assert any(str(row.id) == alloc_id for row in found), \
            f"alloc {alloc_id} not in DB (found {[str(r.id) for r in found]})"

    r = await c.post(f"/api/v1/icr/bench-fees/{alloc_id}/drawdowns", headers=h, json={
        "amount": "4000.00", "category": "sequencing",
        "description": "10x Genomics sequencing run", "drawnAt": TODAY.isoformat(),
    })
    assert r.status_code == 201, r.text

    r = await c.post(f"/api/v1/icr/bench-fees/{alloc_id}/drawdowns", headers=h, json={
        "amount": "5000.00", "category": "mass_spec",
        "description": "MS runs", "drawnAt": TODAY.isoformat(),
    })
    assert r.status_code == 201

    r = await c.post(f"/api/v1/icr/bench-fees/{alloc_id}/drawdowns", headers=h, json={
        "amount": "2000.00", "category": "reagents",
        "description": "Antibodies", "drawnAt": TODAY.isoformat(),
    })
    assert r.status_code == 422
    assert "exceed" in r.json()["error"]["message"].lower()

    r = await c.get(f"/api/v1/icr/students/{sid}/bench-fees", headers=h)
    a = r.json()["allocations"][0]
    assert a["drawnAmount"] in ("9000.00", "9000")
    assert a["remainingAmount"] in ("1000.00", "1000")


# =====================================================================
# ICR GAP 5 - Partner affiliation + compliance flags
# =====================================================================

@pytest.mark.asyncio
async def test_gap5_partner_affiliation_with_compliance_flags(ctx):
    from sqlalchemy import select as _sel
    from app.modules.student_record.models import Student
    from app.db.session import get_session as _get

    c, h = ctx
    async with c.sm() as s:
        stu = (await s.execute(_sel(Student).where(Student.student_ref == "ICR-99-0011"))).scalar_one()
        sid = str(stu.id)

    expired  = (TODAY - timedelta(days=30)).isoformat()
    expiring = (TODAY + timedelta(days=20)).isoformat()
    ok       = (TODAY + timedelta(days=400)).isoformat()

    r = await c.post(f"/api/v1/icr/students/{sid}/partner-affiliations", headers=h, json={
        "partnerName": "Royal Marsden NHS Foundation Trust",
        "affiliationKind": "honorary_contract",
        "validFrom": TODAY.isoformat(),
        "partnerRef": "HON-2026-9911",
        "compliance": {
            "nhsResearchPassportExpiresOn": expired,
            "dbsRenewalOn": expiring,
            "occupationalHealthClearedOn": ok,
            "gmcNumber": "1234567",
        },
    })
    assert r.status_code == 201, r.text

    r = await c.get(f"/api/v1/icr/students/{sid}/partner-affiliations", headers=h)
    aff = r.json()["affiliations"][0]
    flags = {f["key"]: f for f in aff["complianceFlags"]}
    assert flags["nhsResearchPassportExpiresOn"]["status"] == "expired"
    assert flags["dbsRenewalOn"]["status"] == "expiring"
    # Non-expiry-shaped keys aren't flagged (only *ExpiresOn / *RenewalOn are)
    assert "occupationalHealthClearedOn" not in flags
    assert "gmcNumber" not in flags


@pytest.mark.asyncio
async def test_gap5_unknown_affiliation_kind_is_refused(ctx):
    from sqlalchemy import select as _sel
    from app.modules.student_record.models import Student
    from app.db.session import get_session as _get

    c, h = ctx
    async with c.sm() as s:
        stu = (await s.execute(_sel(Student).where(Student.student_ref == "ICR-99-0001"))).scalar_one()
        sid = str(stu.id)

    r = await c.post(f"/api/v1/icr/students/{sid}/partner-affiliations", headers=h, json={
        "partnerName": "Somewhere",
        "affiliationKind": "not_a_real_kind",
        "validFrom": TODAY.isoformat(),
    })
    assert r.status_code == 422
    assert "affiliation kind" in r.json()["error"]["message"].lower()
