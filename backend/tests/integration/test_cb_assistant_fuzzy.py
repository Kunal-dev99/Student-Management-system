"""CB-A — Fuzzy assistant end-to-end: envelope shape + kind dispatch + row-scoped entities."""
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
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.models import Programme, Student


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://",
                              connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        u = User(email="cb@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]

        prog = Programme(name="PhD", code="PHD-CB"); s.add(prog); await s.flush()
        person = Person(given_name="Alice", family_name="Khan", email="alice@t.com")
        s.add(person); await s.flush()
        stu = Student(person_id=person.id, student_ref="CB-1",
                      programme_id=prog.id, start_date=date(2026, 1, 1),
                      status=StudentStatus.active)
        s.add(stu); await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "cb@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h, sm
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_confident_query_returns_answer_with_card_and_trace(ctx):
    c, h, _ = ctx
    r = await c.post("/api/v1/assistant/query", json={"query": "held payments this quarter"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "answer"
    assert body["card"]["spec"] == "finance_lens_held"
    # Trace present and identifies the intent that fired.
    assert body["trace"]["intents"][0]["name"] == "held_payments"
    # Time slot extracted.
    assert body["trace"]["timeSlot"] is not None


@pytest.mark.asyncio
async def test_off_topic_returns_not_understood_with_chips_or_hint(ctx):
    c, h, _ = ctx
    r = await c.post("/api/v1/assistant/query", json={"query": "what's the weather like"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "not_understood"
    # No hallucinated card.
    assert body["card"] is None
    # Hint is honest.
    assert "help" in body["answer"].lower() or "didn't recognise" in body["answer"].lower()


@pytest.mark.asyncio
async def test_entity_anchor_pulls_student_summary_intent(ctx):
    """'alice khan' with weak keywords should still route to student_summary via entity anchor."""
    c, h, _ = ctx
    r = await c.post("/api/v1/assistant/query", json={"query": "alice khan summary"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "answer"
    assert body["trace"]["intents"][0]["name"] == "student_summary"
    # Entity was resolved.
    ents = body["trace"]["entities"]
    assert ents and ents[0]["name"] == "Alice Khan"


@pytest.mark.asyncio
async def test_navigate_intent_picks_target_from_tokens(ctx):
    c, h, _ = ctx
    r = await c.post("/api/v1/assistant/query", json={"query": "go to funding"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "answer"
    assert body["trace"]["intents"][0]["name"] == "navigate"


@pytest.mark.asyncio
async def test_workforce_intent_calls_workforce_tool(ctx):
    c, h, _ = ctx
    r = await c.post("/api/v1/assistant/query", json={"query": "supervisor workload"}, headers=h)
    body = r.json()
    assert body["kind"] == "answer"
    assert body["card"]["spec"] == "workforce_strip"
    assert "totals" in body["card"]["data"]


@pytest.mark.asyncio
async def test_help_endpoint_lists_intents_grouped(ctx):
    c, h, _ = ctx
    r = await c.get("/api/v1/assistant/help", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["groups"]
    all_names = {i["name"] for g in body["groups"] for i in g["intents"]}
    assert "held_payments" in all_names
    assert "supervisor_workforce" in all_names


@pytest.mark.asyncio
async def test_help_intent_returns_the_help_surface_via_query(ctx):
    c, h, _ = ctx
    r = await c.post("/api/v1/assistant/query", json={"query": "what can i ask"}, headers=h)
    body = r.json()
    assert body["kind"] == "answer"
    assert body["card"]["spec"] == "help_surface"
    assert body["card"]["data"]["groups"]


@pytest.mark.asyncio
async def test_response_is_readonly_and_carries_trace(ctx):
    c, h, _ = ctx
    r = await c.post("/api/v1/assistant/query", json={"query": "held payments"}, headers=h)
    body = r.json()
    assert body["readOnly"] is True
    assert "trace" in body and "intents" in body["trace"]


@pytest.mark.asyncio
async def test_no_llm_client_import_reachable_from_assistant():
    """CB-A retires the LLM path. The assistant service must not import anthropic at module load."""
    import importlib, sys
    # Drop anthropic if it happens to be installed so the import fails deterministically.
    if "anthropic" in sys.modules:
        del sys.modules["anthropic"]
    mod = importlib.import_module("app.modules.assistant.service")
    src = open(mod.__file__, encoding="utf-8").read()
    assert "anthropic" not in src.lower(), "LLM path should be retired in CB-A"
