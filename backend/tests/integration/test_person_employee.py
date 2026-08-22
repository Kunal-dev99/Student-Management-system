"""Phase 6.2 + 6.4 — entry route in reporting, and person ↔ employee depth.

- **6.2**: the route a student took to get here survives into Enterprise 360 and the statutory export.
- **6.4**: employee/researcher relationships can be opened and closed with effective dates and a
  source system, one person_id throughout; and inbound HR records match **deterministically** —
  anything ambiguous becomes a task rather than a silent merge.
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
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student


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
        user = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role, pgr]

        prog = Programme(name="PhD", code="PHD"); s.add(prog); await s.flush()

        # A current PGR who will later be employed.
        p = Person(given_name="Dana", family_name="Scholar", email="dana@uni.ac.uk")
        p.relationships = [PersonRelationship(
            relationship_type=PersonRelationshipType.student,
            valid_from=date(2026, 1, 1), valid_to=None)]
        s.add(p); await s.flush()
        ids["person"] = str(p.id)
        st = Student(person_id=p.id, student_ref="PGR-EMP", programme_id=prog.id,
                     start_date=date(2026, 1, 1), study_mode=StudyMode.full_time,
                     status=StudentStatus.active)
        s.add(st); await s.flush()
        ids["student"] = str(st.id)

        # Two people with the same name — an ambiguous HR match.
        for _ in range(2):
            twin = Person(given_name="Sam", family_name="Twin")
            s.add(twin)
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


# --------------------------------------------------------------------------------------
# 6.4 — relationships
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_open_employee_relationship_keeps_one_identity(ctx):
    c, h, ids, _ = ctx
    r = await c.post(f"/api/v1/persons/{ids['person']}/relationships", headers=h, json={
        "relationshipType": "employee", "validFrom": "2026-06-01", "sourceSystem": "hr"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert set(body["currentTypes"]) == {"student", "employee"}      # concurrent, not replaced
    emp = next(x for x in body["relationships"] if x["relationshipType"] == "employee")
    assert emp["validFrom"] == "2026-06-01" and emp["sourceSystem"] == "hr"


@pytest.mark.asyncio
async def test_close_relationship_preserves_history(ctx):
    c, h, ids, _ = ctx
    await c.post(f"/api/v1/persons/{ids['person']}/relationships", headers=h,
                 json={"relationshipType": "employee", "validFrom": "2026-06-01"})
    closed = await c.post(f"/api/v1/persons/{ids['person']}/relationships/employee/close", headers=h)
    assert closed.status_code == 200
    body = closed.json()
    assert body["currentTypes"] == ["student"]                        # employment ended
    emp = next(x for x in body["relationships"] if x["relationshipType"] == "employee")
    assert emp["validTo"] is not None                                 # but the record remains
    assert emp["current"] is False


@pytest.mark.asyncio
async def test_relationships_endpoint_lists_everything_with_dates(ctx):
    c, h, ids, _ = ctx
    await c.post(f"/api/v1/persons/{ids['person']}/relationships", headers=h,
                 json={"relationshipType": "researcher", "validFrom": "2027-01-01"})
    rels = (await c.get(f"/api/v1/persons/{ids['person']}/relationships", headers=h)).json()
    assert {r["relationshipType"] for r in rels} == {"student", "researcher"}
    researcher = next(r for r in rels if r["relationshipType"] == "researcher")
    assert researcher["validFrom"] == "2027-01-01" and researcher["validTo"] is None


# --------------------------------------------------------------------------------------
# 6.4 — HR matching is deterministic, never a guess
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hr_record_matches_on_email_and_links(ctx):
    from app.modules.integration.repository import IntegrationRepository
    from app.modules.integration.service import IntegrationService

    c, h, ids, sm = ctx
    async with sm() as s:
        result = await IntegrationService(IntegrationRepository(s)).apply_hr_employee_record({
            "email": "DANA@uni.ac.uk", "givenName": "Dana", "familyName": "Scholar",
            "startDate": "2026-09-01",
        })
    assert result["status"] == "linked" and result["personId"] == ids["person"]

    rels = (await c.get(f"/api/v1/persons/{ids['person']}/relationships", headers=h)).json()
    current = {r["relationshipType"] for r in rels if r["validTo"] is None}
    assert "employee" in current and "student" in current


@pytest.mark.asyncio
async def test_ambiguous_hr_record_becomes_a_task_not_a_merge(ctx):
    from app.modules.integration.repository import IntegrationRepository
    from app.modules.integration.service import IntegrationService

    c, h, _, sm = ctx
    async with sm() as s:
        result = await IntegrationService(IntegrationRepository(s)).apply_hr_employee_record(
            {"givenName": "Sam", "familyName": "Twin"}
        )
    assert result["status"] == "queued_for_review"
    assert result["candidates"] == 2
    tasks = (await c.get("/api/v1/tasks", headers=h)).json()
    assert any("match hr employee record" in t["title"].lower() for t in tasks)


@pytest.mark.asyncio
async def test_unmatched_hr_record_also_queues(ctx):
    from app.modules.integration.repository import IntegrationRepository
    from app.modules.integration.service import IntegrationService

    c, h, _, sm = ctx
    async with sm() as s:
        result = await IntegrationService(IntegrationRepository(s)).apply_hr_employee_record(
            {"email": "nobody@elsewhere.com", "givenName": "No", "familyName": "Body"}
        )
    assert result["status"] == "queued_for_review" and result["candidates"] == 0


# --------------------------------------------------------------------------------------
# 6.2 — entry route reaches reporting
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_entry_route_appears_in_enterprise_360_and_statutory_export(ctx):
    c, h, ids, _ = ctx
    # Give the person an application so there is a route to report.
    await c.post("/api/v1/applications", headers=h, json={
        "personId": ids["person"], "route": "student_led", "proposalDocumentRef": "p.pdf"})

    e360 = (await c.get("/api/v1/reports/pgr-enterprise-360", headers=h)).json()
    row = next(r for r in e360["population"] if r["studentRef"] == "PGR-EMP")
    assert row["student"]["entryRoute"] == "student_led"

    job = (await c.post("/api/v1/exports", headers=h, json={"kind": "students_statutory"})).json()
    csv_text = (await c.get(f"/api/v1/exports/{job['id']}/download", headers=h)).text
    assert "entry_route" in csv_text.splitlines()[0]      # column present
    assert "student_led" in csv_text
