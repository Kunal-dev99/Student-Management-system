"""F3 — Recruitment depth: references, interviews, offer conditions, visa gate.

What must hold:
- reference request → token URL → referee submits via token → status becomes received
- expired / used token cannot be resubmitted
- interview scheduled + panellist added + outcome recorded → interview completed
- an offer with an unsatisfied condition CANNOT be accepted
- an application with visa_required and no visa_check CANNOT have its offer issued
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.admissions.constants import OfferStatus
from app.modules.admissions.models import Offer
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.recruitment.constants import ApplicationRoute, CandidateStage
from app.modules.recruitment.models import Application
from app.modules.student_record.models import Programme


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)

    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        u = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]

        prog = Programme(name="PhD CS", code="PHD-CS"); s.add(prog); await s.flush()
        person = Person(given_name="Cai", family_name="Lin", email="cai@example.com")
        panellist = Person(given_name="Priya", family_name="Nair", email="priya@example.com")
        s.add_all([person, panellist]); await s.flush()

        appn = Application(person_id=person.id, route=ApplicationRoute.opportunity_led,
                           current_stage=CandidateStage.selected)
        s.add(appn); await s.flush()

        offer = Offer(application_id=appn.id, status=OfferStatus.draft)
        s.add(offer); await s.flush()

        await s.commit()
        ids = {
            "app": str(appn.id), "offer": str(offer.id),
            "person": str(person.id), "panellist": str(panellist.id),
        }

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


# ---------------------------------------------------------------- references

@pytest.mark.asyncio
async def test_reference_request_and_referee_submission(ctx):
    c, h, ids = ctx
    r = await c.post(f"/api/v1/applications/{ids['app']}/references", headers=h, json={
        "refereeName": "Prof Alex Roe", "refereeEmail": "roe@uni.edu",
        "refereeAffiliation": "University of Elsewhere",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    token = body["submitToken"]
    assert body["reference"]["status"] == "requested"
    # Referee submits via the token — no authentication needed
    r = await c.post(f"/api/v1/public/references/{token}", json={
        "responseText": "Strongly recommend. Exceptional research potential.",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "received"
    # Repeat submission is refused
    r = await c.post(f"/api/v1/public/references/{token}", json={"responseText": "again"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_bad_reference_token_is_refused(ctx):
    c, _h, _ids = ctx
    r = await c.post("/api/v1/public/references/nope-not-a-real-token", json={"responseText": "x"})
    assert r.status_code == 404


# ---------------------------------------------------------------- interviews

@pytest.mark.asyncio
async def test_interview_lifecycle(ctx):
    c, h, ids = ctx
    when = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    r = await c.post(f"/api/v1/applications/{ids['app']}/interviews", headers=h, json={
        "scheduledAt": when, "location": "Room 42",
    })
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    # Add a panellist (dedup enforced)
    r = await c.post(f"/api/v1/applications/interviews/{iid}/panellists", headers=h,
                     json={"personId": ids["panellist"], "role": "chair"})
    assert r.status_code == 201
    r = await c.post(f"/api/v1/applications/interviews/{iid}/panellists", headers=h,
                     json={"personId": ids["panellist"]})
    assert r.status_code == 409
    # Record outcome
    r = await c.post(f"/api/v1/applications/interviews/{iid}/outcome", headers=h,
                     json={"outcome": "proceed", "notes": "Strong candidate."})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed" and body["outcome"] == "proceed"


# ---------------------------------------------------------------- conditions

@pytest.mark.asyncio
async def test_accept_refused_while_condition_pending(ctx):
    c, h, ids = ctx
    # Issue the offer first (no visa flag → OK)
    r = await c.post(f"/api/v1/offers/{ids['offer']}/issue", headers=h)
    assert r.status_code == 200
    # Add a pending condition
    r = await c.post(f"/api/v1/offers/{ids['offer']}/conditions", headers=h, json={
        "description": "Pass Masters at 2:1+", "satisfyBy": str(date.today() + timedelta(days=90)),
    })
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    # Try to accept — should be refused
    r = await c.post(f"/api/v1/offers/{ids['offer']}/accept", headers=h, json={"studyMode": "full_time"})
    assert r.status_code == 422
    assert "condition" in r.json()["error"]["message"].lower()

    # Satisfy the condition
    r = await c.post(f"/api/v1/offers/{ids['offer']}/conditions/{cid}/satisfy", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "satisfied"

    # Now accept succeeds
    r = await c.post(f"/api/v1/offers/{ids['offer']}/accept", headers=h, json={"studyMode": "full_time"})
    assert r.status_code in (200, 201), r.text


@pytest.mark.asyncio
async def test_condition_can_be_waived_instead_of_satisfied(ctx):
    c, h, ids = ctx
    await c.post(f"/api/v1/offers/{ids['offer']}/issue", headers=h)
    r = await c.post(f"/api/v1/offers/{ids['offer']}/conditions", headers=h,
                     json={"description": "Provide certified transcript"})
    cid = r.json()["id"]
    r = await c.post(f"/api/v1/offers/{ids['offer']}/conditions/{cid}/waive", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "waived"
    r = await c.post(f"/api/v1/offers/{ids['offer']}/accept", headers=h, json={"studyMode": "full_time"})
    assert r.status_code in (200, 201)


# ---------------------------------------------------------------- visa gate

@pytest.mark.asyncio
async def test_visa_required_blocks_issue_until_check_complete(ctx):
    c, h, ids = ctx
    # Flag the application as visa-required, do NOT complete the check
    r = await c.patch(f"/api/v1/applications/{ids['app']}/visa-check", headers=h, json={
        "feeStatus": "overseas", "visaRequired": True,
    })
    assert r.status_code == 200 and r.json()["visaRequired"] is True
    # Try to issue → refused
    r = await c.post(f"/api/v1/offers/{ids['offer']}/issue", headers=h)
    assert r.status_code == 422
    assert "visa" in r.json()["error"]["message"].lower()
    # Complete the check → issue now succeeds
    await c.patch(f"/api/v1/applications/{ids['app']}/visa-check", headers=h, json={
        "completeVisaCheck": True,
    })
    r = await c.post(f"/api/v1/offers/{ids['offer']}/issue", headers=h)
    assert r.status_code == 200
