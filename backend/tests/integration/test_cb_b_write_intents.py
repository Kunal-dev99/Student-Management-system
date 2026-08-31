"""CB-B — write intents, confirm-before-write, slot memory."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.funding.constants import FundingStatus, FundingType, PaymentStatus
from app.modules.funding.models import FundingArrangement, StipendPayment
from app.modules.fuzzy import pending_write, slot_memory
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.models import Programme, Student


@pytest_asyncio.fixture
async def ctx():
    slot_memory.clear_all()
    pending_write.clear_all()

    eng = create_async_engine("sqlite+aiosqlite://",
                              connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    ids: dict[str, str] = {}
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        # Full admin — has assistant.use + funding.write.
        admin = Role(name="Institution Administrator"); s.add(admin); await s.flush()
        await s.refresh(admin, ["permissions"])
        admin.permissions = list(perms.values())
        # Read-only role — assistant.use but NO funding.write.
        ro = Role(name="Read-only"); s.add(ro); await s.flush()
        await s.refresh(ro, ["permissions"])
        ro.permissions = [perms["assistant.use"], perms["student.read"], perms["funding.read"]]

        ua = User(email="admin@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(ua); await s.flush(); await s.refresh(ua, ["roles"]); ua.roles = [admin]
        ur = User(email="ro@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(ur); await s.flush(); await s.refresh(ur, ["roles"]); ur.roles = [ro]

        prog = Programme(name="PhD", code="PHD-CBB"); s.add(prog); await s.flush()
        person = Person(given_name="Alice", family_name="Khan", email="alice@t.com")
        s.add(person); await s.flush()
        stu = Student(person_id=person.id, student_ref="CBB-1",
                      programme_id=prog.id, start_date=date(2026, 1, 1),
                      status=StudentStatus.active)
        s.add(stu); await s.flush()
        arr = FundingArrangement(
            student_id=stu.id, funding_type=FundingType.research_council,
            stipend_amount=Decimal("18000"), currency="GBP",
            valid_from=date(2026, 1, 1), status=FundingStatus.active,
        )
        s.add(arr); await s.flush()
        pay = StipendPayment(
            student_id=stu.id, arrangement_id=arr.id, sequence=1,
            due_date=date.today() + timedelta(days=30),
            amount=Decimal("1500"), currency="GBP",
            status=PaymentStatus.scheduled,
        )
        s.add(pay); await s.commit()
        ids |= {"student": str(stu.id), "payment": str(pay.id)}

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


@pytest.mark.asyncio
async def test_write_intent_stages_pending_and_does_not_mutate(ctx):
    """approve Alice's payment → confirm_write envelope; the DB row must be unchanged."""
    c, token, ids, sm = ctx
    h = await token("admin@t.com")
    r = await c.post("/api/v1/assistant/query",
                     json={"query": "approve Alice's payment"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "confirm_write"
    assert body["card"]["spec"] == "confirm_approve_payment"
    assert body["card"]["data"]["action"] == "approve_payment"
    # Payment must still be scheduled — mutation only happens after /confirm.
    async with sm() as s:
        row = (await s.execute(
            select(StipendPayment).where(StipendPayment.id == uuid.UUID(ids["payment"]))
        )).scalar_one()
        assert row.status == PaymentStatus.scheduled
    # A pendingId is issued.
    assert body["card"]["data"]["pendingId"]


@pytest.mark.asyncio
async def test_confirm_actually_executes_the_pending_write(ctx):
    c, token, ids, sm = ctx
    h = await token("admin@t.com")
    stage = (await c.post("/api/v1/assistant/query",
                           json={"query": "approve Alice's payment"}, headers=h)).json()
    pid = stage["card"]["data"]["pendingId"]
    r = await c.post("/api/v1/assistant/confirm", json={"pendingId": pid}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "answer"
    assert "Done" in body["answer"]
    async with sm() as s:
        row = (await s.execute(
            select(StipendPayment).where(StipendPayment.id == uuid.UUID(ids["payment"]))
        )).scalar_one()
        assert row.status == PaymentStatus.approved


@pytest.mark.asyncio
async def test_pending_id_is_single_use(ctx):
    c, token, _, _ = ctx
    h = await token("admin@t.com")
    stage = (await c.post("/api/v1/assistant/query",
                           json={"query": "approve Alice's payment"}, headers=h)).json()
    pid = stage["card"]["data"]["pendingId"]
    first = await c.post("/api/v1/assistant/confirm", json={"pendingId": pid}, headers=h)
    assert first.json()["kind"] == "answer"
    second = await c.post("/api/v1/assistant/confirm", json={"pendingId": pid}, headers=h)
    assert second.json()["kind"] == "not_understood"    # already consumed


@pytest.mark.asyncio
async def test_write_intent_refused_without_permission(ctx):
    """A user with assistant.use but no funding.write gets a permission refusal, not a stage."""
    c, token, _, sm = ctx
    h = await token("ro@t.com")
    r = await c.post("/api/v1/assistant/query",
                     json={"query": "approve Alice's payment"}, headers=h)
    body = r.json()
    assert body["kind"] == "not_understood"
    assert "funding.change" in body["answer"]


@pytest.mark.asyncio
async def test_confirm_by_a_different_user_is_refused(ctx):
    """User A stages, user B cannot confirm — pending records are user-bound."""
    c, token, _, _ = ctx
    h_a = await token("admin@t.com")
    h_b = await token("ro@t.com")
    stage = (await c.post("/api/v1/assistant/query",
                           json={"query": "approve Alice's payment"}, headers=h_a)).json()
    pid = stage["card"]["data"]["pendingId"]
    r = await c.post("/api/v1/assistant/confirm", json={"pendingId": pid}, headers=h_b)
    assert r.json()["kind"] == "not_understood"     # user mismatch → treated as expired


@pytest.mark.asyncio
async def test_write_intent_without_entity_falls_to_clarify(ctx):
    """A bare 'approve payment' with no student named should clarify, not silently pick one."""
    c, token, _, _ = ctx
    h = await token("admin@t.com")
    r = await c.post("/api/v1/assistant/query",
                     json={"query": "approve the payment"}, headers=h)
    body = r.json()
    # Depending on scoring this can be clarify or not_understood — never confirm_write.
    assert body["kind"] in {"clarify", "not_understood"}


@pytest.mark.asyncio
async def test_slot_memory_binds_pronoun_to_prior_entity(ctx):
    """First: resolve Alice. Second: 'her payments' → binds back to Alice via slot memory."""
    c, token, _, _ = ctx
    h = await token("admin@t.com")
    first = (await c.post("/api/v1/assistant/query",
                           json={"query": "Alice Khan summary", "sessionId": "s1"},
                           headers=h)).json()
    assert first["trace"]["entities"][0]["name"] == "Alice Khan"
    second = (await c.post("/api/v1/assistant/query",
                            json={"query": "her held payments", "sessionId": "s1"},
                            headers=h)).json()
    # The pronoun was substituted BEFORE routing, so the entity resolves again on the follow-up.
    assert second["trace"]["entities"], "pronoun should have been rewritten to 'Alice Khan'"
    assert second["trace"]["entities"][0]["name"] == "Alice Khan"


@pytest.mark.asyncio
async def test_slot_memory_is_isolated_per_session(ctx):
    """A different sessionId does NOT inherit the memory."""
    c, token, _, _ = ctx
    h = await token("admin@t.com")
    await c.post("/api/v1/assistant/query",
                 json={"query": "Alice Khan summary", "sessionId": "sA"}, headers=h)
    # New session — no prior context, "her" should not resolve.
    r = (await c.post("/api/v1/assistant/query",
                       json={"query": "her held payments", "sessionId": "sB"},
                       headers=h)).json()
    # Either no entities OR the pronoun stayed literal and produced no match.
    assert not r["trace"]["entities"]
