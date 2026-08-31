"""Inbound partner messages are APPLIED, not just logged (CIO gap matrix #12).

The analysis rated Research/Finance/HR integration AMBER with a specific caution: *"validate real
partner mappings/reconciliation, not just adapters."* Logging an inbound message proved the
transport worked but changed nothing in the domain. These tests pin the mapping.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.models import Person, PersonRelationship
from app.modules.research.models import ResearchAward


def _signed(body: dict) -> tuple[bytes, dict]:
    raw = json.dumps(body).encode()
    sig = hmac.new(get_settings().app_secret_key.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"X-Signature": sig, "Content-Type": "application/json"}


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        pgr = Role(name="PGR Administrator"); s.add(pgr); await s.flush()
        await s.refresh(pgr, ["permissions"]); pgr.permissions = list(perms.values())
        user = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role, pgr]

        p = Person(given_name="Nadia", family_name="Khan", email="nadia@uni.ac.uk")
        p.relationships = [PersonRelationship(
            relationship_type=PersonRelationshipType.student,
            valid_from=date(2026, 1, 1), valid_to=None)]
        s.add(p); await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h, sm
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_research_award_message_creates_the_award(ctx):
    c, h, sm = ctx
    body = {"sourceId": "RS-1001", "eventType": "award.updated",
            "payload": {"awardRef": "EP/INBOUND/1", "title": "Inbound Award",
                        "startDate": "2026-04-01", "value": "750000", "currency": "GBP",
                        "externalRef": "RS-1001"}}
    raw, headers = _signed(body)
    r = await c.post("/api/v1/integration/webhooks/research", content=raw, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "processed"
    assert r.json()["applied"]["awardRef"] == "EP/INBOUND/1"

    async with sm() as s:
        award = (await s.execute(
            select(ResearchAward).where(ResearchAward.award_ref == "EP/INBOUND/1")
        )).scalar_one()
        assert award.source_system == "research"      # mastered externally
        assert award.synced_at is not None

    # And it is read-only through the API, as an externally-mastered record must be.
    awards = (await c.get("/api/v1/research-awards", headers=h)).json()
    inbound = next(a for a in awards if a["awardRef"] == "EP/INBOUND/1")
    assert inbound["readOnly"] is True


@pytest.mark.asyncio
async def test_hr_message_links_the_employee_identity(ctx):
    c, h, _ = ctx
    body = {"sourceId": "HR-77", "eventType": "employee.appointed",
            "payload": {"email": "nadia@uni.ac.uk", "givenName": "Nadia",
                        "familyName": "Khan", "startDate": "2026-09-01"}}
    raw, headers = _signed(body)
    r = await c.post("/api/v1/integration/webhooks/hr", content=raw, headers=headers)
    assert r.status_code == 200
    assert r.json()["applied"]["status"] == "linked"

    persons = (await c.get("/api/v1/persons?search=Nadia", headers=h)).json()["data"]
    rels = (await c.get(f"/api/v1/persons/{persons[0]['id']}/relationships", headers=h)).json()
    current = {x["relationshipType"] for x in rels if x["validTo"] is None}
    assert current == {"student", "employee"}          # one person, two live identities


@pytest.mark.asyncio
async def test_ambiguous_hr_message_queues_instead_of_merging(ctx):
    c, h, _ = ctx
    body = {"sourceId": "HR-78", "eventType": "employee.appointed",
            "payload": {"givenName": "Unknown", "familyName": "Person"}}
    raw, headers = _signed(body)
    r = await c.post("/api/v1/integration/webhooks/hr", content=raw, headers=headers)
    assert r.json()["applied"]["status"] == "queued_for_review"
    tasks = (await c.get("/api/v1/tasks", headers=h)).json()
    assert any("match hr employee record" in t["title"].lower() for t in tasks)


@pytest.mark.asyncio
async def test_unrecognised_message_is_still_recorded(ctx):
    """Nothing is lost just because we have no handler for it."""
    c, h, _ = ctx
    body = {"sourceId": "FIN-1", "eventType": "invoice.raised", "payload": {"x": 1}}
    raw, headers = _signed(body)
    r = await c.post("/api/v1/integration/webhooks/finance", content=raw, headers=headers)
    assert r.json()["status"] == "logged_only"

    logs = (await c.get("/api/v1/integration/logs", headers=h)).json()["logs"]
    assert any(l["sourceId"] == "FIN-1" for l in logs)


@pytest.mark.asyncio
async def test_bad_payload_is_logged_with_the_error_not_silently_dropped(ctx):
    c, h, _ = ctx
    body = {"sourceId": "RS-BAD", "eventType": "award.updated", "payload": {"title": "no ref"}}
    raw, headers = _signed(body)
    r = await c.post("/api/v1/integration/webhooks/research", content=raw, headers=headers)
    assert r.json()["status"] == "logged_with_error"
    assert "awardRef is required" in r.json()["error"]

    logs = (await c.get("/api/v1/integration/logs", headers=h)).json()["logs"]
    entry = next(l for l in logs if l["sourceId"] == "RS-BAD")
    assert entry["status"] == "failed"          # visible in the integration log for triage


@pytest.mark.asyncio
async def test_replayed_message_is_still_idempotent(ctx):
    c, h, _ = ctx
    body = {"sourceId": "RS-2002", "eventType": "award.updated",
            "payload": {"awardRef": "EP/DUP/2", "title": "Once"}}
    raw, headers = _signed(body)
    assert (await c.post("/api/v1/integration/webhooks/research", content=raw, headers=headers)).json()["status"] == "processed"
    assert (await c.post("/api/v1/integration/webhooks/research", content=raw, headers=headers)).json()["status"] == "duplicate"


# --------------------------------------------------------------------------------------
# Reconciliation view (Phase 7, item R3)
# --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reconciliation_surfaces_what_needs_a_human(ctx):
    """An administrator should see stuck outbound work, failed inbound messages, and the
    HR records waiting on a person — in one place."""
    c, h, _ = ctx

    # A malformed research message -> failed inbound.
    bad = {"sourceId": "REC-BAD", "eventType": "award.updated", "payload": {"title": "no ref"}}
    raw, headers = _signed(bad)
    await c.post("/api/v1/integration/webhooks/research", content=raw, headers=headers)

    # An unmatchable HR record -> a task waiting on a person.
    unmatched = {"sourceId": "REC-HR", "eventType": "employee.appointed",
                 "payload": {"givenName": "Nobody", "familyName": "Here"}}
    raw2, headers2 = _signed(unmatched)
    await c.post("/api/v1/integration/webhooks/hr", content=raw2, headers=headers2)

    r = await c.get("/api/v1/integration/reconciliation", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["healthy"] is False
    assert body["issueCount"] >= 2
    assert any(f["sourceId"] == "REC-BAD" for f in body["inbound"]["failed"])
    assert "awardRef is required" in body["inbound"]["failed"][0]["error"]
    assert body["awaitingPeople"]["unmatchedHrRecords"]          # a person must decide
    assert "research" in body["inbound"]["bySystem"]


@pytest.mark.asyncio
async def test_reconciliation_counts_outbound_backlog(ctx):
    c, h, _ = ctx
    body = (await c.get("/api/v1/integration/reconciliation", headers=h)).json()
    assert "pending" in body["outbound"]
    assert "deadLettered" in body["outbound"]
    assert body["windowDays"] == 30



# ============================================================================
# W3 - Finance inbound handler (payment.confirmed / payment.rejected)
# ============================================================================

async def _seed_payment(sm, *, status=None, finance_ref: str | None = None):
    """Seed a stipend arrangement + one payment in the given state; return payment id."""
    from datetime import date as _d
    from decimal import Decimal
    from app.modules.funding.constants import FundingStatus, FundingType, PaymentStatus
    from app.modules.funding.models import FundingArrangement, StipendPayment
    from app.modules.student_record.models import Programme, Student
    from app.modules.person.models import Person
    async with sm() as s:
        prog = Programme(name="PhD CS", code="PHD-CS-W3"); s.add(prog); await s.flush()
        person = Person(given_name="Fin", family_name="Test", email="fin@t.com")
        s.add(person); await s.flush()
        stu = Student(person_id=person.id, student_ref="FIN-W3-1",
                      programme_id=prog.id, start_date=_d(2026, 1, 1))
        s.add(stu); await s.flush()
        arr = FundingArrangement(
            student_id=stu.id, funding_type=FundingType.research_council,
            stipend_amount=Decimal("18000"), currency="GBP",
            valid_from=_d(2026, 1, 1), status=FundingStatus.active,
        )
        s.add(arr); await s.flush()
        pay = StipendPayment(
            student_id=stu.id, arrangement_id=arr.id, sequence=1,
            due_date=_d(2026, 8, 1), amount=Decimal("1500"), currency="GBP",
            status=(status or PaymentStatus.approved),
            finance_reference=finance_ref,
        )
        s.add(pay); await s.commit()
        return str(pay.id)


@pytest.mark.asyncio
async def test_w3_finance_payment_confirmed_marks_paid(ctx):
    """A payment.confirmed inbound message flips the row to PAID with the finance ref."""
    from sqlalchemy import select as _sel
    from app.modules.funding.constants import PaymentStatus
    from app.modules.funding.models import StipendPayment
    c, h, sm = ctx
    pid = await _seed_payment(sm)

    body = {
        "sourceId": "FIN-CONF-1",
        "eventType": "payment.confirmed",
        "payload": {"paymentId": pid, "paidOn": "2026-08-15", "financeReference": "FIN-REF-42"},
    }
    raw, headers = _signed(body)
    r = await c.post("/api/v1/integration/webhooks/finance", content=raw, headers=headers)
    assert r.status_code == 200, r.text
    body_out = r.json()
    assert body_out["status"] == "processed", body_out
    assert body_out["applied"]["action"] == "marked_paid"

    async with sm() as s:
        row = (await s.execute(_sel(StipendPayment).where(StipendPayment.id == uuid.UUID(pid)))).scalar_one()
        assert row.status == PaymentStatus.paid
        assert row.finance_reference == "FIN-REF-42"
        assert row.paid_on.isoformat() == "2026-08-15"


@pytest.mark.asyncio
async def test_w3_finance_payment_confirmed_is_idempotent(ctx):
    c, h, sm = ctx
    pid = await _seed_payment(sm)
    body = {"sourceId": "FIN-CONF-2", "eventType": "payment.confirmed",
            "payload": {"paymentId": pid, "paidOn": "2026-08-15", "financeReference": "R1"}}
    raw, headers = _signed(body)
    r = await c.post("/api/v1/integration/webhooks/finance", content=raw, headers=headers)
    assert r.json()["status"] == "processed"
    # Second delivery with a NEW sourceId (partner resent) — the row is already paid, so the
    # handler returns "already_paid" without exploding.
    body2 = {"sourceId": "FIN-CONF-2-REPEAT", "eventType": "payment.confirmed",
             "payload": {"paymentId": pid, "paidOn": "2026-08-15"}}
    raw2, headers2 = _signed(body2)
    r2 = await c.post("/api/v1/integration/webhooks/finance", content=raw2, headers=headers2)
    assert r2.json()["status"] == "processed"
    assert r2.json()["applied"]["action"] == "already_paid"


@pytest.mark.asyncio
async def test_w3_finance_payment_rejected_holds_row_with_reason(ctx):
    from sqlalchemy import select as _sel
    from app.modules.funding.constants import PaymentStatus
    from app.modules.funding.models import StipendPayment
    c, h, sm = ctx
    pid = await _seed_payment(sm)

    body = {"sourceId": "FIN-REJ-1", "eventType": "payment.rejected",
            "payload": {"paymentId": pid, "reason": "invalid cost centre"}}
    raw, headers = _signed(body)
    r = await c.post("/api/v1/integration/webhooks/finance", content=raw, headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "processed"
    assert r.json()["applied"]["action"] == "held"

    async with sm() as s:
        row = (await s.execute(_sel(StipendPayment).where(StipendPayment.id == uuid.UUID(pid)))).scalar_one()
        assert row.status == PaymentStatus.held
        assert row.note and "Finance rejected" in row.note and "invalid cost centre" in row.note


@pytest.mark.asyncio
async def test_w3_finance_lookup_by_reference_when_no_uuid(ctx):
    """Finance may only carry its own reference; we should still find the row."""
    from app.modules.funding.constants import PaymentStatus
    c, h, sm = ctx
    pid = await _seed_payment(sm, finance_ref="FIN-KNOWN-99")

    body = {"sourceId": "FIN-LOOKUP-1", "eventType": "payment.confirmed",
            "payload": {"financeReference": "FIN-KNOWN-99", "paidOn": "2026-09-01"}}
    raw, headers = _signed(body)
    r = await c.post("/api/v1/integration/webhooks/finance", content=raw, headers=headers)
    assert r.json()["status"] == "processed"
    assert r.json()["applied"]["paymentId"] == pid


@pytest.mark.asyncio
async def test_w3_finance_bad_payload_logs_with_error(ctx):
    """A payload without paymentId or financeReference lands as logged_with_error, not dropped."""
    c, h, sm = ctx
    body = {"sourceId": "FIN-BAD-1", "eventType": "payment.confirmed", "payload": {}}
    raw, headers = _signed(body)
    r = await c.post("/api/v1/integration/webhooks/finance", content=raw, headers=headers)
    assert r.json()["status"] == "logged_with_error"
    assert "paymentId or financeReference" in r.json()["error"]

    logs = (await c.get("/api/v1/integration/logs", headers=h)).json()["logs"]
    entry = next(l for l in logs if l["sourceId"] == "FIN-BAD-1")
    assert entry["status"] == "failed"


@pytest.mark.asyncio
async def test_w3_finance_reject_after_paid_is_refused(ctx):
    """A payment.rejected after settlement is nonsense — the handler refuses so the incident
    is triaged rather than silently rewriting a paid row."""
    c, h, sm = ctx
    pid = await _seed_payment(sm)
    # First confirm
    body = {"sourceId": "FIN-P1", "eventType": "payment.confirmed",
            "payload": {"paymentId": pid, "paidOn": "2026-08-15"}}
    raw, headers = _signed(body)
    await c.post("/api/v1/integration/webhooks/finance", content=raw, headers=headers)
    # Then try to reject it
    body2 = {"sourceId": "FIN-P1-REJ", "eventType": "payment.rejected",
             "payload": {"paymentId": pid, "reason": "should not apply"}}
    raw2, headers2 = _signed(body2)
    r = await c.post("/api/v1/integration/webhooks/finance", content=raw2, headers=headers2)
    assert r.json()["status"] == "logged_with_error"
    assert "already paid" in r.json()["error"].lower()
