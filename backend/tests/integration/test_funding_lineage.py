"""Phase 6.3 — funding lineage and integrity (CIO vision GAP-03).

The single trace: Student → Research Project → Research Award → Funder → Funding Arrangement →
Stipend. And then: does the chain make sense? Each finding must carry the dates or amounts that
produced it, so it can be defended rather than merely displayed.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

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
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.research.models import ResearchAward
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, ResearchProject, Student

START = date(2026, 1, 1)
EXPECTED_END = date(2029, 1, 1)


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
        user = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]

        prog = Programme(name="PhD", code="PHD"); s.add(prog)
        funder = FundingSource(name="UKRI EPSRC", funder_type="research_council"); s.add(funder)
        await s.flush()
        ids["funder"] = str(funder.id)

        award = ResearchAward(
            award_ref="EP/L/1", title="Lineage Award", funder_id=funder.id,
            start_date=START, end_date=date(2030, 1, 1), value=Decimal("100000"), currency="GBP",
        )
        s.add(award); await s.flush()
        ids["award"] = str(award.id)

        # Three students: one clean, one with a funding gap, one funded past the award.
        for key, ref, name in (("clean", "PGR-CLEAN", "Clea"), ("gap", "PGR-GAP", "Gappy"),
                               ("short", "PGR-SHORT", "Shorty")):
            person = Person(given_name=name, family_name="Test"); s.add(person); await s.flush()
            st = Student(
                person_id=person.id, student_ref=ref, programme_id=prog.id,
                start_date=START, expected_end_date=EXPECTED_END,
                study_mode=StudyMode.full_time, status=StudentStatus.active,
            )
            s.add(st); await s.flush()
            ids[key] = str(st.id)
            s.add(ResearchProject(
                student_id=st.id, research_topic=f"{name}'s work",
                research_award_id=award.id, start_date=START,
            ))

        # clean: one arrangement covering the whole journey, attributed to the award.
        s.add(FundingArrangement(
            student_id=__import__("uuid").UUID(ids["clean"]), funding_type=FundingType.research_council,
            funding_source_id=funder.id, research_award_id=award.id,
            stipend_amount=Decimal("18000"), currency="GBP",
            valid_from=START, valid_to=EXPECTED_END, status=FundingStatus.active,
        ))
        # gap: two arrangements with a 3-month hole between them.
        import uuid as _u
        s.add(FundingArrangement(
            student_id=_u.UUID(ids["gap"]), funding_type=FundingType.research_council,
            funding_source_id=funder.id, research_award_id=award.id,
            valid_from=START, valid_to=date(2027, 1, 1), status=FundingStatus.ended,
        ))
        s.add(FundingArrangement(
            student_id=_u.UUID(ids["gap"]), funding_type=FundingType.research_council,
            funding_source_id=funder.id, research_award_id=award.id,
            valid_from=date(2027, 4, 1), valid_to=EXPECTED_END, status=FundingStatus.active,
        ))
        # short: funding stops a year before the student is due to finish.
        s.add(FundingArrangement(
            student_id=_u.UUID(ids["short"]), funding_type=FundingType.research_council,
            funding_source_id=funder.id, research_award_id=award.id,
            valid_from=START, valid_to=date(2028, 1, 1), status=FundingStatus.active,
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
        yield c, h, ids, sm
    app.dependency_overrides.clear()
    await eng.dispose()


async def _lineage(c, h, sid):
    r = await c.get(f"/api/v1/students/{sid}/funding-lineage", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _codes(result):
    return {f["code"] for f in result["findings"]}


# --------------------------------------------------------------------------------------
# The trace
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_chain_student_to_stipend(ctx):
    c, h, ids, _ = ctx
    lin = await _lineage(c, h, ids["clean"])

    assert lin["student"]["studentRef"] == "PGR-CLEAN"
    assert lin["project"]["award"]["awardRef"] == "EP/L/1"
    assert lin["project"]["award"]["funder"]["name"] == "UKRI EPSRC"   # every hop present
    assert len(lin["arrangements"]) == 1
    assert lin["arrangements"][0]["award"]["awardRef"] == "EP/L/1"
    assert lin["arrangements"][0]["fundingSource"]["name"] == "UKRI EPSRC"
    assert lin["complete"] is True                                     # no errors


@pytest.mark.asyncio
async def test_stipend_totals_roll_up_through_the_chain(ctx):
    c, h, ids, _ = ctx
    lin = await _lineage(c, h, ids["clean"])
    arrangement_id = lin["arrangements"][0]["id"]

    await c.post(f"/api/v1/funding/{arrangement_id}/payments/schedule", headers=h,
                 json={"frequency": "annual", "instalments": 3, "annualAmount": "18000"})
    payments = (await c.get(f"/api/v1/funding/{arrangement_id}/payments", headers=h)).json()
    await c.post(f"/api/v1/funding/payments/{payments[0]['id']}/paid", headers=h, json={})

    lin = await _lineage(c, h, ids["clean"])
    assert lin["arrangements"][0]["instalments"] == 3
    assert lin["arrangements"][0]["paidTotal"] == "18000.00"
    assert lin["totals"]["committed"] == "54000.00"


# --------------------------------------------------------------------------------------
# Integrity findings
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_funding_gap_is_an_error_with_the_dates_that_caused_it(ctx):
    c, h, ids, _ = ctx
    lin = await _lineage(c, h, ids["gap"])
    gap = next(f for f in lin["findings"] if f["code"] == "funding_gap")
    assert gap["severity"] == "error"
    assert gap["detail"]["days"] == 90
    assert gap["detail"]["from_"] == "2027-01-01" and gap["detail"]["to"] == "2027-04-01"
    assert lin["complete"] is False


@pytest.mark.asyncio
async def test_funding_ending_before_expected_end_is_flagged(ctx):
    c, h, ids, _ = ctx
    lin = await _lineage(c, h, ids["short"])
    short = next(f for f in lin["findings"] if f["code"] == "funding_ends_before_expected_end")
    assert short["severity"] == "error"
    assert short["detail"]["shortfallDays"] == (EXPECTED_END - date(2028, 1, 1)).days
    assert short["detail"]["expectedEnd"] == EXPECTED_END.isoformat()


@pytest.mark.asyncio
async def test_clean_student_has_no_errors(ctx):
    c, h, ids, _ = ctx
    lin = await _lineage(c, h, ids["clean"])
    assert [f for f in lin["findings"] if f["severity"] == "error"] == []


@pytest.mark.asyncio
async def test_funding_outliving_its_award_is_flagged(ctx):
    c, h, ids, sm = ctx
    import uuid as _u
    from sqlalchemy import select

    async with sm() as s:
        arr = (await s.execute(select(FundingArrangement).where(
            FundingArrangement.student_id == _u.UUID(ids["clean"])))).scalars().first()
        arr.valid_to = date(2031, 1, 1)          # award ends 2030-01-01
        await s.commit()

    lin = await _lineage(c, h, ids["clean"])
    f = next(f for f in lin["findings"] if f["code"] == "funding_outlives_award")
    assert f["severity"] == "error" and f["detail"]["awardRef"] == "EP/L/1"


@pytest.mark.asyncio
async def test_arrangement_with_finance_refs_but_no_award_is_flagged(ctx):
    c, h, ids, sm = ctx
    import uuid as _u
    from sqlalchemy import select

    async with sm() as s:
        arr = (await s.execute(select(FundingArrangement).where(
            FundingArrangement.student_id == _u.UUID(ids["clean"])))).scalars().first()
        arr.research_award_id = None
        arr.project_code = "PRJ-77"              # finance refs but nothing to attribute them to
        await s.commit()

    lin = await _lineage(c, h, ids["clean"])
    f = next(f for f in lin["findings"] if f["code"] == "arrangement_award_unlinked")
    assert f["severity"] == "warning" and f["detail"]["projectCode"] == "PRJ-77"


@pytest.mark.asyncio
async def test_committed_stipend_exceeding_award_value_is_an_error(ctx):
    c, h, ids, _ = ctx
    lin = await _lineage(c, h, ids["clean"])
    arrangement_id = lin["arrangements"][0]["id"]
    # Award value is 100,000 — schedule 120,000 against it.
    await c.post(f"/api/v1/funding/{arrangement_id}/payments/schedule", headers=h,
                 json={"frequency": "annual", "instalments": 6, "annualAmount": "20000"})
    lin = await _lineage(c, h, ids["clean"])
    f = next(f for f in lin["findings"] if f["code"] == "stipend_exceeds_award_value")
    assert f["severity"] == "error"
    assert f["detail"]["awardValue"] == "100000.00"


@pytest.mark.asyncio
async def test_missing_project_is_reported(ctx):
    c, h, ids, sm = ctx
    import uuid as _u
    from sqlalchemy import select

    async with sm() as s:
        proj = (await s.execute(select(ResearchProject).where(
            ResearchProject.student_id == _u.UUID(ids["clean"])))).scalars().first()
        await s.delete(proj); await s.commit()

    lin = await _lineage(c, h, ids["clean"])
    assert lin["project"] is None
    assert "no_project" in _codes(lin)


# --------------------------------------------------------------------------------------
# Cohort view — the question with no screen
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cohort_integrity_lists_only_students_with_problems(ctx):
    c, h, ids, _ = ctx
    r = await c.get("/api/v1/reports/funding-integrity", headers=h)
    assert r.status_code == 200
    body = r.json()

    refs = {s["studentRef"] for s in body["students"]}
    assert "PGR-GAP" in refs and "PGR-SHORT" in refs
    assert "PGR-CLEAN" not in refs            # a healthy chain is not noise
    assert body["checked"] == 3
    assert body["errors"] >= 2
    # Errors sort ahead of warnings so the worst cases are seen first.
    assert body["students"][0]["worstSeverity"] == "error"
    assert all(s["findings"] for s in body["students"])


@pytest.mark.asyncio
async def test_cohort_integrity_can_filter_to_errors(ctx):
    c, h, _, _ = ctx
    body = (await c.get("/api/v1/reports/funding-integrity?severity=error", headers=h)).json()
    assert all(f["severity"] == "error" for s in body["students"] for f in s["findings"])


@pytest.mark.asyncio
async def test_admission_populates_the_lineage_automatically(ctx):
    """An opportunity-led student should arrive with their project already linked to the award."""
    c, h, ids, _ = ctx
    opp = (await c.post("/api/v1/opportunities", headers=h, json={
        "title": "Funded PhD", "positionsAvailable": 1, "expectedDurationMonths": 36,
        "researchAwardId": ids["award"]})).json()
    for step in ("approved", "open"):
        await c.post(f"/api/v1/opportunities/{opp['id']}/transition", headers=h, json={"toStatus": step})

    person = (await c.post("/api/v1/persons", headers=h,
                           json={"givenName": "New", "familyName": "Starter"})).json()
    app_row = (await c.post("/api/v1/applications", headers=h, json={
        "personId": person["id"], "route": "opportunity_led",
        "researchOpportunityId": opp["id"]})).json()
    offer = (await c.post(f"/api/v1/applications/{app_row['id']}/offer", headers=h, json={})).json()
    await c.post(f"/api/v1/offers/{offer['id']}/issue", headers=h)
    student = (await c.post(f"/api/v1/offers/{offer['id']}/accept", headers=h,
                            json={"startDate": "2026-10-01"})).json()

    lin = await _lineage(c, h, student["id"])
    assert lin["project"] is not None
    assert lin["project"]["award"]["awardRef"] == "EP/L/1"   # linked with no manual step
