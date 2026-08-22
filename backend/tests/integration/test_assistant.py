"""Phase 5.1 — read-only assistant.

The safety properties matter more than the phrasing: the assistant must be permission-gated,
must never widen a user's row scope, and must not be able to change anything.
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
from app.modules.funding.models import FundingArrangement
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Student
from app.modules.supervision.constants import SupervisionStatus, SupervisorRole
from app.modules.supervision.models import SupervisionMeeting, SupervisorRelationship


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

        admin_role = Role(name="Institution Administrator"); s.add(admin_role); await s.flush()
        await s.refresh(admin_role, ["permissions"]); admin_role.permissions = list(perms.values())
        # A supervisor deliberately WITHOUT assistant.use, to prove the gate.
        sup_role = Role(name="Supervisor"); s.add(sup_role); await s.flush()
        await s.refresh(sup_role, ["permissions"])
        sup_role.permissions = [perms["student.read"], perms["person.read"], perms["progression.read"]]

        admin = User(email="admin@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(admin); await s.flush(); await s.refresh(admin, ["roles"]); admin.roles = [admin_role]

        elena = Person(given_name="Elena", family_name="Ford")
        p_a = Person(given_name="Marcus", family_name="Bell")
        p_b = Person(given_name="Priya", family_name="Nair")
        s.add_all([elena, p_a, p_b]); await s.flush()

        sup = User(email="sup@t.com", password_hash=hash_password("pw"), is_active=True, person_id=elena.id)
        s.add(sup); await s.flush(); await s.refresh(sup, ["roles"]); sup.roles = [sup_role]

        a = Student(person_id=p_a.id, student_ref="PGR-2026-AAA111", study_mode=StudyMode.full_time,
                    status=StudentStatus.registered, start_date=date(2025, 1, 1))
        b = Student(person_id=p_b.id, student_ref="PGR-2026-BBB222", study_mode=StudyMode.full_time,
                    status=StudentStatus.registered, start_date=date(2025, 1, 1))
        s.add_all([a, b]); await s.flush()
        ids |= {"a": str(a.id), "b": str(b.id), "elena": str(elena.id)}

        # Elena supervises A only.
        s.add(SupervisorRelationship(
            student_id=a.id, supervisor_person_id=elena.id, role=SupervisorRole.primary,
            status=SupervisionStatus.active, valid_from=date(2025, 1, 1),
        ))
        # A met recently; B has never met.
        s.add(SupervisionMeeting(student_id=a.id, supervisor_person_id=elena.id, met_on=date.today()))
        # B's funding expires soon; A has none.
        s.add(FundingArrangement(
            student_id=b.id, funding_type=FundingType.research_council, valid_from=date(2025, 1, 1),
            valid_to=date.today() + timedelta(days=30), status=FundingStatus.active,
        ))
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
        yield c, token, ids
    app.dependency_overrides.clear()
    await eng.dispose()


async def _ask(c, h, q):
    return await c.post("/api/v1/assistant/query", headers=h, json={"query": q})


@pytest.mark.asyncio
async def test_assistant_requires_permission(ctx):
    c, token, _ = ctx
    hs = await token("sup@t.com")   # supervisor has no assistant.use
    r = await _ask(c, hs, "my tasks")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_student_ref_resolves_without_a_model(ctx):
    c, token, ids = ctx
    h = await token("admin@t.com")
    r = await _ask(c, h, "PGR-2026-AAA111")
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "rules"      # no model call needed
    assert "Marcus Bell" in body["answer"]
    assert body["links"][0]["href"] == f"/students/{ids['a']}"
    assert body["readOnly"] is True


@pytest.mark.asyncio
async def test_navigation_without_a_model(ctx):
    c, token, _ = ctx
    h = await token("admin@t.com")
    body = (await _ask(c, h, "go to funding")).json()
    assert body["path"] == "rules"
    assert body["links"][0]["href"] == "/funding"


@pytest.mark.asyncio
async def test_pinned_tasks_intent(ctx):
    c, token, _ = ctx
    h = await token("admin@t.com")
    body = (await _ask(c, h, "my tasks")).json()
    assert body["path"] == "rules"
    assert "open task" in body["answer"]


@pytest.mark.asyncio
async def test_unparseable_question_declines_with_suggestions(ctx):
    c, token, _ = ctx
    h = await token("admin@t.com")
    body = (await _ask(c, h, "explain the reasoning behind our last away day")).json()
    # The LLM fallback is off by default — it must decline honestly, not fabricate.
    assert body["path"] == "unmatched"
    assert body["data"]["didYouMean"]           # offers concrete alternatives
    assert body["data"]["llmEnabled"] is False


@pytest.mark.asyncio
async def test_natural_language_cohort_query_end_to_end(ctx):
    """The headline capability, answered by rules alone: a sentence -> a filtered, explained list."""
    c, token, ids = ctx
    h = await token("admin@t.com")
    body = (await _ask(c, h, "which students have no supervision meeting in 90 days?")).json()

    assert body["path"] == "rules"                      # zero tokens, no data left the server
    assert body["understood"] == "no supervision meeting in 90 days"   # readback for verification
    assert body["data"]["count"] == 1
    row = body["data"]["students"][0]
    assert row["studentRef"] == "PGR-2026-BBB222"       # never met; Marcus met today
    assert any("no supervision meeting" in r for r in row["reasons"])


@pytest.mark.asyncio
async def test_two_condition_query_binds_each_window(ctx):
    c, token, _ = ctx
    h = await token("admin@t.com")
    body = (await _ask(
        c, h, "students with no supervision meeting in 90 days and funding expiring in 6 months"
    )).json()
    assert body["path"] == "rules"
    assert "90 days" in body["understood"] and "180 days" in body["understood"]
    assert body["data"]["count"] == 1
    assert len(body["data"]["students"][0]["reasons"]) == 2   # both conditions explained


@pytest.mark.asyncio
async def test_cohort_query_explains_why_each_student_matched(ctx):
    """The capability the UI has no screen for — exercised directly through the tool layer."""
    from app.core.principal import Principal
    from app.modules.assistant.tools import ToolBox
    from app.modules.identity.repository import IdentityRepository
    from app.modules.identity.service import IdentityService

    c, token, ids = ctx
    # Build the admin principal the same way a request would.
    h = await token("admin@t.com")
    raw = h["Authorization"].split(" ", 1)[1]

    from app.db.session import get_read_session as _grs
    agen = app.dependency_overrides[_grs]()
    session = await agen.__anext__()
    try:
        principal = await IdentityService(IdentityRepository(session)).principal_from_access_token(raw)
        box = ToolBox(session, principal)

        never_met = await box.execute("cohort_query", {"noSupervisionMeetingInDays": 90})
        refs = {s["studentRef"] for s in never_met["students"]}
        assert "PGR-2026-BBB222" in refs          # never met
        assert "PGR-2026-AAA111" not in refs      # met today
        assert any("no supervision meeting" in r for r in never_met["students"][0]["reasons"])

        # Combined AND filter: never met AND funding expiring — only B qualifies.
        both = await box.execute("cohort_query", {
            "noSupervisionMeetingInDays": 90, "fundingExpiringWithinDays": 60,
        })
        assert both["count"] == 1
        assert both["students"][0]["studentRef"] == "PGR-2026-BBB222"
        assert len(both["students"][0]["reasons"]) == 2   # both conditions explained
        assert "no active funding" not in str(both["filters"])
    finally:
        await agen.aclose()


@pytest.mark.asyncio
async def test_cohort_query_respects_row_scope(ctx):
    """A supervisor must never see beyond their supervisees, even via the assistant's tools."""
    from app.modules.assistant.tools import ToolBox
    from app.modules.identity.repository import IdentityRepository
    from app.modules.identity.service import IdentityService
    from app.db.session import get_read_session as _grs

    c, token, ids = ctx
    hs = await token("sup@t.com")
    raw = hs["Authorization"].split(" ", 1)[1]

    agen = app.dependency_overrides[_grs]()
    session = await agen.__anext__()
    try:
        principal = await IdentityService(IdentityRepository(session)).principal_from_access_token(raw)
        box = ToolBox(session, principal)
        # Elena supervises only student A, so an unfiltered cohort query must return just A.
        res = await box.execute("cohort_query", {})
        refs = {s["studentRef"] for s in res["students"]}
        assert refs == {"PGR-2026-AAA111"}
        # And a name search for a student outside her scope finds nothing.
        found = await box.execute("find_student", {"query": "Priya"})
        assert found["count"] == 0
    finally:
        await agen.aclose()
