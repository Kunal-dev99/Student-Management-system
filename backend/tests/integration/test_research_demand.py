"""Phase 6.1 — Research Demand → PGR Position (CIO vision GAP-01).

The vision starts before the student exists. What must hold:
- an award is a **reference**, mastered in the Research system; externally-sourced awards are
  read-only here (guardrail: this is not grants management)
- demand can exist with or without an award (strategic demand is legitimate)
- a position knows where it came from, and how many places remain
- accepting an offer **takes a place**; an over-filled position is refused
- the expected end date is **derived from the advertised duration**, giving suspensions a baseline
- lineage answers "where did this come from, and who did it produce?" — and names any gaps
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
from app.modules.funding.models import FundingSource
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.models import Person, PersonRelationship
from app.modules.research.models import ResearchAward
from app.modules.student_record.models import Department, Programme


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

        dept = Department(name="CS", code="CS"); s.add(dept); await s.flush()
        prog = Programme(name="PhD CS", code="PHD-CS", department_id=dept.id); s.add(prog)
        funder = FundingSource(name="UKRI EPSRC", funder_type="research_council"); s.add(funder)
        await s.flush()
        ids |= {"department": str(dept.id), "programme": str(prog.id), "funder": str(funder.id)}

        # An award that arrived from the Research system — read-only here.
        external = ResearchAward(
            award_ref="EP/EXT/1", title="Externally mastered award", funder_id=funder.id,
            source_system="research", external_ref="RS-991",
        )
        s.add(external); await s.flush()
        ids["external_award"] = str(external.id)

        people = [Person(given_name=n, family_name="Applicant", email=f"{n.lower()}@t.com")
                  for n in ("Ann", "Ben", "Cara")]
        for p in people:
            p.relationships = [PersonRelationship(
                relationship_type=PersonRelationshipType.applicant,
                valid_from=date(2026, 1, 1), valid_to=None)]
        s.add_all(people); await s.commit()
        ids["people"] = [str(p.id) for p in people]

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h, ids
    app.dependency_overrides.clear()
    await eng.dispose()


async def _award(c, h, ref="EP/X/1", funder_id=None):
    return (await c.post("/api/v1/research-awards", headers=h, json={
        "awardRef": ref, "title": "Robotics for Care", "value": "1200000", "currency": "GBP",
        "startDate": "2026-01-01", "endDate": "2030-01-01", "funderId": funder_id})).json()


async def _demand(c, h, award_id=None, places=1):
    return (await c.post("/api/v1/research-demands", headers=h, json={
        "title": "Researcher for robotics workstream",
        "researchAwardId": award_id, "requestedPlaces": places,
        "justification": "Award requires a PGR researcher from year 1",
        "targetStartDate": "2026-10-01"})).json()


async def _position(c, h, demand_id=None, award_id=None, places=1, months=42):
    """Create a position and open it for recruitment (draft -> approved -> open)."""
    opp = (await c.post("/api/v1/opportunities", headers=h, json={
        "title": "PhD in Assistive Robotics", "positionsAvailable": places,
        "expectedDurationMonths": months,
        "researchDemandId": demand_id, "researchAwardId": award_id})).json()
    for step in ("approved", "open"):
        await c.post(f"/api/v1/opportunities/{opp['id']}/transition", headers=h, json={"toStatus": step})
    return opp


async def _fill_position(c, h, opp_id, person_id, programme_id, start="2026-10-01"):
    app_row = (await c.post("/api/v1/applications", headers=h, json={
        "personId": person_id, "route": "opportunity_led", "researchOpportunityId": opp_id})).json()
    offer = (await c.post(f"/api/v1/applications/{app_row['id']}/offer", headers=h, json={})).json()
    await c.post(f"/api/v1/offers/{offer['id']}/issue", headers=h)
    return await c.post(f"/api/v1/offers/{offer['id']}/accept", headers=h,
                        json={"programmeId": programme_id, "startDate": start})


# --------------------------------------------------------------------------------------
# Awards — reference records, not grants management
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_award_can_be_recorded_manually(ctx):
    c, h, _ = ctx
    a = await _award(c, h)
    assert a["awardRef"] == "EP/X/1"
    assert a["readOnly"] is False        # locally held, so editable


@pytest.mark.asyncio
async def test_duplicate_award_reference_refused(ctx):
    c, h, _ = ctx
    await _award(c, h, "EP/DUP/1")
    r = await c.post("/api/v1/research-awards", headers=h,
                     json={"awardRef": "EP/DUP/1", "title": "Another"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_award_sync_from_the_research_system(ctx):
    """The primary path: the Research system is the source of truth and overwrites local values."""
    from app.modules.research.repository import ResearchRepository
    from app.modules.research.service import ResearchService
    from app.db.session import get_read_session as _grs

    c, h, ids = ctx
    agen = app.dependency_overrides[_grs]()
    session = await agen.__anext__()
    try:
        svc = ResearchService(ResearchRepository(session))
        first = await svc.upsert_from_research_system({
            "awardRef": "EP/SYNC/9", "title": "Synced award",
            "startDate": "2026-04-01", "value": "500000", "currency": "GBP",
            "externalRef": "RS-42",
        })
        assert first.source_system == "research" and first.synced_at is not None

        # A later sync updates the same record rather than creating a duplicate.
        again = await svc.upsert_from_research_system({
            "awardRef": "EP/SYNC/9", "title": "Synced award (renamed upstream)",
        })
        assert again.id == first.id
        assert again.title == "Synced award (renamed upstream)"
        assert again.value is not None                     # untouched fields survive
    finally:
        await agen.aclose()

    # And it is read-only through the API.
    awards = (await c.get("/api/v1/research-awards", headers=h)).json()
    synced = next(a for a in awards if a["awardRef"] == "EP/SYNC/9")
    assert synced["readOnly"] is True
    assert (await c.patch(f"/api/v1/research-awards/{synced['id']}", headers=h,
                          json={"title": "nope"})).status_code == 409


@pytest.mark.asyncio
async def test_externally_mastered_award_is_read_only(ctx):
    """Guardrail: the Research system owns it; we hold a reference."""
    c, h, ids = ctx
    awards = (await c.get("/api/v1/research-awards", headers=h)).json()
    ext = next(a for a in awards if a["id"] == ids["external_award"])
    assert ext["readOnly"] is True and ext["sourceSystem"] == "research"

    r = await c.patch(f"/api/v1/research-awards/{ids['external_award']}", headers=h,
                      json={"title": "Renamed locally"})
    assert r.status_code == 409
    assert "maintained in the research system" in r.json()["error"]["message"].lower()


# --------------------------------------------------------------------------------------
# Demand
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_demand_may_be_strategic_with_no_award(ctx):
    c, h, _ = ctx
    d = await _demand(c, h, award_id=None)
    assert d["researchAwardId"] is None and d["status"] == "identified"


@pytest.mark.asyncio
async def test_demand_lifecycle_transitions_are_enforced(ctx):
    c, h, _ = ctx
    d = await _demand(c, h)
    # identified -> positioned is not allowed; it must be approved first.
    bad = await c.post(f"/api/v1/research-demands/{d['id']}/transition", headers=h,
                       json={"toStatus": "positioned"})
    assert bad.status_code == 422
    for step in ("approved", "positioned"):
        ok = await c.post(f"/api/v1/research-demands/{d['id']}/transition", headers=h,
                          json={"toStatus": step})
        assert ok.status_code == 200 and ok.json()["status"] == step


@pytest.mark.asyncio
async def test_demand_requires_at_least_one_place(ctx):
    c, h, _ = ctx
    r = await c.post("/api/v1/research-demands", headers=h,
                     json={"title": "Nothing", "requestedPlaces": 0})
    assert r.status_code == 422


# --------------------------------------------------------------------------------------
# Position places
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_accepting_an_offer_takes_a_place_and_fills_the_position(ctx):
    c, h, ids = ctx
    award = await _award(c, h)
    demand = await _demand(c, h, award["id"])
    await c.post(f"/api/v1/research-demands/{demand['id']}/transition", headers=h, json={"toStatus": "approved"})
    await c.post(f"/api/v1/research-demands/{demand['id']}/transition", headers=h, json={"toStatus": "positioned"})
    opp = await _position(c, h, demand["id"], award["id"], places=1)

    accepted = await _fill_position(c, h, opp["id"], ids["people"][0], ids["programme"])
    assert accepted.status_code == 201, accepted.text

    lineage = (await c.get(f"/api/v1/opportunities/{opp['id']}/lineage", headers=h)).json()
    assert lineage["position"]["positionsFilled"] == 1
    assert lineage["position"]["positionsRemaining"] == 0
    assert lineage["position"]["status"] == "filled"          # stops recruiting
    assert lineage["demand"]["status"] == "filled"            # the need is satisfied


@pytest.mark.asyncio
async def test_over_filling_a_position_is_refused(ctx):
    c, h, ids = ctx
    opp = await _position(c, h, places=1)
    first = await _fill_position(c, h, opp["id"], ids["people"][0], ids["programme"])
    assert first.status_code == 201
    second = await _fill_position(c, h, opp["id"], ids["people"][1], ids["programme"])
    assert second.status_code == 409
    assert "already full" in second.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_multi_place_position_accepts_up_to_its_limit(ctx):
    c, h, ids = ctx
    opp = await _position(c, h, places=2)
    assert (await _fill_position(c, h, opp["id"], ids["people"][0], ids["programme"])).status_code == 201
    assert (await _fill_position(c, h, opp["id"], ids["people"][1], ids["programme"])).status_code == 201
    assert (await _fill_position(c, h, opp["id"], ids["people"][2], ids["programme"])).status_code == 409


# --------------------------------------------------------------------------------------
# Expected end date derived from the advertised duration (gap found in Phase 6.5)
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expected_end_date_is_derived_from_the_position_duration(ctx):
    c, h, ids = ctx
    opp = await _position(c, h, months=42)
    accepted = await _fill_position(c, h, opp["id"], ids["people"][0], ids["programme"], start="2026-10-01")
    student = accepted.json()
    # 2026-10-01 + 42 months = 2030-04-01
    assert student["expectedEndDate"] == "2030-04-01"
    assert student["originalExpectedEndDate"] == "2030-04-01"   # baseline for suspensions


# --------------------------------------------------------------------------------------
# Lineage
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_lineage_traces_award_to_student(ctx):
    c, h, ids = ctx
    award = await _award(c, h, funder_id=ids["funder"])
    demand = await _demand(c, h, award["id"])
    opp = await _position(c, h, demand["id"], award["id"])
    await _fill_position(c, h, opp["id"], ids["people"][0], ids["programme"])

    lin = (await c.get(f"/api/v1/opportunities/{opp['id']}/lineage", headers=h)).json()
    assert lin["award"]["awardRef"] == "EP/X/1"
    assert lin["funder"]["name"] == "UKRI EPSRC"          # full chain to the funder
    assert lin["demand"]["id"] == demand["id"]
    assert lin["position"]["id"] == opp["id"]
    assert lin["studentsProduced"] == 1
    assert lin["applications"][0]["student"]["personName"] == "Ann Applicant"
    assert lin["gaps"] == []                                   # complete chain


@pytest.mark.asyncio
async def test_lineage_reports_gaps_rather_than_hiding_them(ctx):
    """A position raised with no demand and no award must SAY so."""
    c, h, _ = ctx
    opp = await _position(c, h, demand_id=None, award_id=None)
    lin = (await c.get(f"/api/v1/opportunities/{opp['id']}/lineage", headers=h)).json()
    assert lin["award"] is None and lin["demand"] is None
    assert any("not linked to a research demand" in g for g in lin["gaps"])
    assert any("no research award is linked" in g.lower() for g in lin["gaps"])
