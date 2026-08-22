"""Phase 6.0 — evidence for the CIO vision gap analysis.

The gap analysis rated two requirements AMBER because the implementation reference "did not prove"
them. The model turned out to be present; these tests are the missing proof, and they pin the
behaviour so it cannot regress:

- **GAP-02** two distinct entry routes: Route A (opportunity-led, from an advertised PGR position)
  and Route B (student-led, from a person and their own research proposal) both reach `student`
  through the same admission lifecycle.
- **GAP-04** person ↔ employee continuity: a PGR can become an employee/researcher **without a
  second identity** — one person_id, concurrent effective-dated relationships, full history.

Also covers the route-integrity rules added in 6.0.3.
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
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.models import Person, PersonRelationship
from app.modules.recruitment.constants import OpportunityStatus
from app.modules.recruitment.models import ResearchOpportunity
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
        prog = Programme(name="PhD CS", code="PHD-CS", department_id=dept.id)
        s.add(prog); await s.flush()
        ids["programme"] = str(prog.id)

        # An advertised PGR position, for Route A.
        opp = ResearchOpportunity(
            title="PhD in Robotics", department_id=dept.id, status=OpportunityStatus.open,
            positions_available=1, expected_duration_months=42,
        )
        s.add(opp); await s.flush()
        ids["opportunity"] = str(opp.id)

        # Two applicants: one per route.
        route_a = Person(given_name="Ada", family_name="Position", email="ada@t.com")
        route_b = Person(given_name="Bo", family_name="Proposal", email="bo@t.com")
        for p in (route_a, route_b):
            p.relationships = [PersonRelationship(
                relationship_type=PersonRelationshipType.applicant,
                valid_from=date(2026, 1, 1), valid_to=None,
            )]
        s.add_all([route_a, route_b]); await s.commit()
        ids["person_a"] = str(route_a.id)
        ids["person_b"] = str(route_b.id)

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


async def _drive_to_student(c, h, application_id, programme_id):
    """The shared admission lifecycle both routes must converge on: offer -> issue -> accept.

    Accepting returns 201 because it *creates* the student, reusing the applicant's person_id.
    """
    offer = await c.post(f"/api/v1/applications/{application_id}/offer", headers=h, json={})
    assert offer.status_code == 201, offer.text
    oid = offer.json()["id"]
    issued = await c.post(f"/api/v1/offers/{oid}/issue", headers=h)
    assert issued.status_code == 200, issued.text
    return await c.post(f"/api/v1/offers/{oid}/accept", headers=h, json={})


# --------------------------------------------------------------------------------------
# GAP-02 — two distinct entry routes
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_route_a_opportunity_led_reaches_student(ctx):
    """Route A: an advertised PGR position leads to a student."""
    c, h, ids, _ = ctx
    created = await c.post("/api/v1/applications", headers=h, json={
        "personId": ids["person_a"], "route": "opportunity_led",
        "researchOpportunityId": ids["opportunity"],
    })
    assert created.status_code == 201, created.text
    assert created.json()["route"] == "opportunity_led"

    accepted = await _drive_to_student(c, h, created.json()["id"], ids["programme"])
    assert accepted.status_code == 201, accepted.text

    students = (await c.get("/api/v1/students", headers=h)).json()["data"]
    assert any(s["personId"] == ids["person_a"] for s in students)   # same person_id carried through


@pytest.mark.asyncio
async def test_route_b_student_led_reaches_student(ctx):
    """Route B: a person with their own research proposal, no advertised position."""
    c, h, ids, _ = ctx
    created = await c.post("/api/v1/applications", headers=h, json={
        "personId": ids["person_b"], "route": "student_led",
        "proposalDocumentRef": "proposal-bo.pdf",
    })
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["route"] == "student_led"
    assert body["researchOpportunityId"] is None          # genuinely no position involved
    assert body["proposalDocumentRef"] == "proposal-bo.pdf"

    accepted = await _drive_to_student(c, h, body["id"], ids["programme"])
    assert accepted.status_code == 201, accepted.text

    students = (await c.get("/api/v1/students", headers=h)).json()["data"]
    assert any(s["personId"] == ids["person_b"] for s in students)


@pytest.mark.asyncio
async def test_both_routes_share_one_admission_lifecycle(ctx):
    """The two routes must converge — same stages, same offer/admission machinery."""
    c, h, ids, _ = ctx
    a = (await c.post("/api/v1/applications", headers=h, json={
        "personId": ids["person_a"], "route": "opportunity_led",
        "researchOpportunityId": ids["opportunity"]})).json()
    b = (await c.post("/api/v1/applications", headers=h, json={
        "personId": ids["person_b"], "route": "student_led",
        "proposalDocumentRef": "p.pdf"})).json()
    for app_id in (a["id"], b["id"]):
        assert (await _drive_to_student(c, h, app_id, ids["programme"])).status_code == 201
    assert (await c.get("/api/v1/students", headers=h)).json()["page"]["total"] == 2


# --- route integrity (BE-6.0.3) ---

@pytest.mark.asyncio
async def test_opportunity_led_requires_an_opportunity(ctx):
    c, h, ids, _ = ctx
    r = await c.post("/api/v1/applications", headers=h,
                     json={"personId": ids["person_a"], "route": "opportunity_led"})
    assert r.status_code == 400
    assert "research opportunity" in r.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_student_led_must_not_reference_an_opportunity(ctx):
    c, h, ids, _ = ctx
    r = await c.post("/api/v1/applications", headers=h, json={
        "personId": ids["person_b"], "route": "student_led",
        "researchOpportunityId": ids["opportunity"]})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_student_led_needs_area_or_proposal(ctx):
    c, h, ids, _ = ctx
    r = await c.post("/api/v1/applications", headers=h,
                     json={"personId": ids["person_b"], "route": "student_led"})
    assert r.status_code == 400
    assert "proposal" in r.json()["error"]["message"].lower()


# --------------------------------------------------------------------------------------
# GAP-04 — person ↔ employee/researcher continuity
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pgr_becomes_employee_without_a_second_identity(ctx):
    """A PGR who takes up employment keeps ONE person_id, with concurrent relationships."""
    from app.modules.person.repository import PersonRepository
    from app.modules.person.service import PersonService

    c, h, ids, sm = ctx
    # Become a student first (Route B).
    created = (await c.post("/api/v1/applications", headers=h, json={
        "personId": ids["person_b"], "route": "student_led", "proposalDocumentRef": "p.pdf"})).json()
    await _drive_to_student(c, h, created["id"], ids["programme"])

    import uuid as _uuid
    person_id = _uuid.UUID(ids["person_b"])

    # Now the same person is employed as a researcher — open the relationship WITHOUT
    # closing the student one (end_type=None), which is the whole point.
    async with sm() as s:
        svc = PersonService(PersonRepository(s))
        await svc.transition_identity(
            person_id, end_type=None, open_type=PersonRelationshipType.employee,
            source_system="hr", on_date=date(2026, 6, 1),
        )
        await s.commit()

    timeline = (await c.get(f"/api/v1/persons/{ids['person_b']}/timeline", headers=h)).json()
    kinds = [e["detail"]["relationshipType"] for e in timeline["entries"] if e["kind"] == "relationship"]
    assert "student" in kinds and "employee" in kinds        # concurrent, not replaced
    assert "applicant" in kinds                              # history preserved

    current = [
        e["detail"]["relationshipType"] for e in timeline["entries"]
        if e["kind"] == "relationship" and e["detail"]["validTo"] is None
    ]
    assert set(current) == {"student", "employee"}           # both live at once
    # And still exactly one person.
    persons = (await c.get("/api/v1/persons", headers=h)).json()["data"]
    assert sum(1 for p in persons if p["id"] == ids["person_b"]) == 1


@pytest.mark.asyncio
async def test_employee_relationship_records_effective_dates_and_source(ctx):
    """HR-sourced relationships must be effective-dated and attributable."""
    from app.modules.person.repository import PersonRepository
    from app.modules.person.service import PersonService
    import uuid as _uuid

    c, h, ids, sm = ctx
    async with sm() as s:
        svc = PersonService(PersonRepository(s))
        await svc.transition_identity(
            _uuid.UUID(ids["person_a"]), end_type=None,
            open_type=PersonRelationshipType.researcher,
            source_system="hr", on_date=date(2026, 3, 15),
        )
        await s.commit()

    timeline = (await c.get(f"/api/v1/persons/{ids['person_a']}/timeline", headers=h)).json()
    researcher = next(
        e for e in timeline["entries"]
        if e["kind"] == "relationship" and e["detail"]["relationshipType"] == "researcher"
    )
    assert researcher["detail"]["validFrom"] == "2026-03-15"
    assert researcher["detail"]["validTo"] is None
