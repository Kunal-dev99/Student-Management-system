"""Funding arrangements over time (BE-1.8).

A change closes the current arrangement and opens a new one, preserving history (arch §8.9).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.modules.funding.models import FundingSource
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Student

PERMS = ["student.read", "funding.read", "funding.change"]


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def ctx(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        perms = [Permission(code=c) for c in PERMS]
        s.add_all(perms); await s.flush()
        role = Role(name="PGR Administrator")
        s.add(role); await s.flush(); await s.refresh(role, ["permissions"]); role.permissions = perms
        user = User(email="u@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]
        src = FundingSource(name="UKRI", funder_type="research_council")
        person = Person(given_name="Sam", family_name="R")
        s.add_all([src, person]); await s.flush()
        student = Student(person_id=person.id, student_ref="PGR-F", study_mode=StudyMode.full_time, status=StudentStatus.registered)
        s.add(student); await s.commit()
        ids = {"student": str(student.id), "source": str(src.id)}

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/v1/auth/login", json={"email": "u@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield client, h, ids
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_and_list_funding(ctx):
    client, h, ids = ctx
    r = await client.post(
        f"/api/v1/students/{ids['student']}/funding", headers=h,
        json={"fundingType": "research_council", "fundingSourceId": ids["source"], "stipendAmount": "19000.00", "currency": "GBP"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "active"
    assert body["fundingSourceName"] == "UKRI"

    r = await client.get(f"/api/v1/students/{ids['student']}/funding", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_change_preserves_history(ctx):
    client, h, ids = ctx
    first = (await client.post(
        f"/api/v1/students/{ids['student']}/funding", headers=h,
        json={"fundingType": "research_council", "stipendAmount": "19000", "currency": "GBP"},
    )).json()

    r = await client.post(
        f"/api/v1/funding/{first['id']}/change", headers=h,
        json={"fundingType": "university_scholarship", "stipendAmount": "21000", "currency": "GBP"},
    )
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["status"] == "active" and new["validTo"] is None

    arrangements = (await client.get(f"/api/v1/students/{ids['student']}/funding", headers=h)).json()
    assert len(arrangements) == 2
    by_status = {a["status"]: a for a in arrangements}
    assert by_status["changed"]["validTo"] is not None      # old one closed
    assert by_status["active"]["fundingType"] == "university_scholarship"


@pytest.mark.asyncio
async def test_end_funding(ctx):
    client, h, ids = ctx
    a = (await client.post(
        f"/api/v1/students/{ids['student']}/funding", headers=h,
        json={"fundingType": "self_funded"},
    )).json()
    r = await client.post(f"/api/v1/funding/{a['id']}/end", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "ended" and r.json()["validTo"] is not None


# --- Phase 4B.7 — cost centres, stipend payment schedule, fee waivers ---

async def _funded(client, h, ids, amount="24000"):
    return (await client.post(
        f"/api/v1/students/{ids['student']}/funding", headers=h,
        json={"fundingType": "research_council", "fundingSourceId": ids["source"],
              "stipendAmount": amount, "currency": "GBP", "validFrom": "2026-01-15",
              "costCentre": "CC-1234", "projectCode": "PRJ-99", "funderReference": "EP/X/1",
              "contributionPct": 100},
    )).json()


@pytest.mark.asyncio
async def test_finance_fields_round_trip(ctx):
    client, h, ids = ctx
    a = await _funded(client, h, ids)
    assert a["costCentre"] == "CC-1234" and a["projectCode"] == "PRJ-99"
    assert a["funderReference"] == "EP/X/1" and a["contributionPct"] == 100


@pytest.mark.asyncio
async def test_generate_monthly_schedule_and_pay(ctx):
    client, h, ids = ctx
    a = await _funded(client, h, ids, amount="24000")
    r = await client.post(f"/api/v1/funding/{a['id']}/payments/schedule", headers=h,
                          json={"frequency": "monthly"})
    assert r.status_code == 201, r.text
    rows = r.json()
    assert len(rows) == 12
    assert rows[0]["amount"] == "2000.00" and rows[0]["currency"] == "GBP"
    assert rows[0]["dueDate"] == "2026-01-15" and rows[1]["dueDate"] == "2026-02-15"
    assert all(p["status"] == "scheduled" for p in rows)

    first = rows[0]["id"]
    approved = await client.post(f"/api/v1/funding/payments/{first}/approve", headers=h)
    assert approved.status_code == 200 and approved.json()["status"] == "approved"

    paid = await client.post(f"/api/v1/funding/payments/{first}/paid", headers=h,
                             json={"paidOn": "2026-01-16", "financeReference": "FIN-001"})
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid" and paid.json()["financeReference"] == "FIN-001"
    # Paid instalments cannot be reverted.
    assert (await client.post(f"/api/v1/funding/payments/{first}/status", headers=h,
                              json={"status": "held"})).status_code == 422

    summary = (await client.get(f"/api/v1/students/{ids['student']}/payment-summary", headers=h)).json()
    assert summary["instalments"] == 12
    assert summary["paidTotal"] == "2000.00"
    assert summary["committedTotal"] == "24000.00"
    assert summary["outstandingTotal"] == "22000.00"


@pytest.mark.asyncio
async def test_quarterly_schedule_and_reschedule_guard(ctx):
    client, h, ids = ctx
    a = await _funded(client, h, ids, amount="20000")
    rows = (await client.post(f"/api/v1/funding/{a['id']}/payments/schedule", headers=h,
                              json={"frequency": "quarterly"})).json()
    assert len(rows) == 4 and rows[0]["amount"] == "5000.00"
    assert rows[1]["dueDate"] == "2026-04-15"

    # Re-generating before anything is paid is fine (replaces the schedule).
    again = await client.post(f"/api/v1/funding/{a['id']}/payments/schedule", headers=h,
                              json={"frequency": "annual"})
    assert again.status_code == 201 and len(again.json()) == 1

    # Once an instalment is paid, regeneration is refused.
    pid = again.json()[0]["id"]
    await client.post(f"/api/v1/funding/payments/{pid}/paid", headers=h, json={})
    blocked = await client.post(f"/api/v1/funding/{a['id']}/payments/schedule", headers=h,
                                json={"frequency": "monthly"})
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_ending_funding_cancels_unpaid_instalments(ctx):
    client, h, ids = ctx
    a = await _funded(client, h, ids)
    await client.post(f"/api/v1/funding/{a['id']}/payments/schedule", headers=h, json={"frequency": "monthly"})
    await client.post(f"/api/v1/funding/{a['id']}/end", headers=h)
    rows = (await client.get(f"/api/v1/funding/{a['id']}/payments", headers=h)).json()
    assert all(p["status"] == "cancelled" for p in rows)


@pytest.mark.asyncio
async def test_fee_waivers(ctx):
    client, h, ids = ctx
    bad = await client.post(f"/api/v1/students/{ids['student']}/fee-waivers", headers=h,
                            json={"kind": "full_fee"})
    assert bad.status_code == 422  # needs an amount or a percentage

    w = await client.post(f"/api/v1/students/{ids['student']}/fee-waivers", headers=h,
                          json={"kind": "partial_fee", "percentage": 50, "academicYear": "2026/27",
                                "note": "Departmental contribution"})
    assert w.status_code == 201 and w.json()["approved"] is False
    wid = w.json()["id"]

    approved = await client.post(f"/api/v1/funding/fee-waivers/{wid}/approve", headers=h)
    assert approved.status_code == 200 and approved.json()["approved"] is True
    # Double approval is refused.
    assert (await client.post(f"/api/v1/funding/fee-waivers/{wid}/approve", headers=h)).status_code == 409

    listed = (await client.get(f"/api/v1/students/{ids['student']}/fee-waivers", headers=h)).json()
    assert len(listed) == 1 and listed[0]["percentage"] == 50
