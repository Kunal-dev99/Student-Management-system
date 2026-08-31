"""CB-C — Unmatched-query telemetry: redacted logging + admin review workflow."""
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
        admin = Role(name="Institution Administrator"); s.add(admin); await s.flush()
        await s.refresh(admin, ["permissions"]); admin.permissions = list(perms.values())
        u = User(email="admin@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [admin]

        prog = Programme(name="PhD", code="PHD-CBC"); s.add(prog); await s.flush()
        per = Person(given_name="Alice", family_name="Khan", email="alice.khan@t.com")
        s.add(per); await s.flush()
        stu = Student(person_id=per.id, student_ref="PGR-2026-XYZ",
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
        r = await c.post("/api/v1/auth/login", json={"email": "admin@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h, sm
    app.dependency_overrides.clear()
    await eng.dispose()


def test_redactor_scrubs_names_emails_uuids_and_refs():
    from app.modules.fuzzy.telemetry import redact
    q = ("Show me Alice Khan's stuff at alice.khan@t.com — ref PGR-2026-XYZ "
         "and uuid 12345678-1234-1234-1234-123456789abc plus 987654")
    out = redact(q, entity_names=["Alice Khan"])
    assert "Alice" not in out
    assert "Khan" not in out
    assert "alice.khan" not in out
    assert "PGR-2026-XYZ" not in out
    assert "12345678-1234-1234-1234-123456789abc" not in out
    assert "987654" not in out
    # Sentinels still present.
    assert "<name>" in out and "<email>" in out and "<ref>" in out
    assert "<uuid>" in out and "<n>" in out


@pytest.mark.asyncio
async def test_unmatched_query_is_logged_redacted(ctx):
    c, h, sm = ctx
    # A gibberish query — will hit not_understood.
    r = await c.post("/api/v1/assistant/query",
                     json={"query": "explain the reasoning behind our last away day"},
                     headers=h)
    assert r.status_code == 200
    assert r.json()["kind"] == "not_understood"

    logs = (await c.get("/api/v1/assistant/telemetry", headers=h)).json()
    assert logs["entries"]
    first = logs["entries"][0]
    assert first["reviewedAt"] is None
    assert first["originalLength"] > 0
    # Suggested intents were captured (may be empty list, that's ok).
    assert isinstance(first["suggestedIntents"], list)


@pytest.mark.asyncio
async def test_query_with_pii_is_redacted_before_log(ctx):
    """A query with a student ref + email that hits no intent should log with both scrubbed."""
    c, h, sm = ctx
    # Off-topic query with an email + a ref of a student that doesn't exist. No intent fires,
    # no entity resolves → logged verbatim (then redacted before write).
    await c.post("/api/v1/assistant/query",
                 json={"query": "explain the reasoning behind memo at random@bar.com re NOPE-9999-ZZZ"},
                 headers=h)
    logs = (await c.get("/api/v1/assistant/telemetry", headers=h)).json()["entries"]
    assert logs, "expected the query to have been logged"
    joined = " ".join(e["queryRedacted"] for e in logs)
    # PII scrubbed, sentinels present.
    assert "random@bar.com" not in joined
    assert "NOPE-9999-ZZZ" not in joined
    assert "<email>" in joined and "<ref>" in joined


@pytest.mark.asyncio
async def test_admin_can_assign_an_unmatched_query_to_an_intent(ctx):
    c, h, _ = ctx
    await c.post("/api/v1/assistant/query",
                 json={"query": "explain the reasoning behind our last away day"}, headers=h)
    entry = (await c.get("/api/v1/assistant/telemetry", headers=h)).json()["entries"][0]
    eid = entry["id"]
    r = await c.post(f"/api/v1/assistant/telemetry/{eid}/assign",
                     json={"assignedIntent": "help",
                            "synonymNote": "map 'away day' to help until it's a real intent"},
                     headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "reviewed"

    # The reviewed row drops off the default (unreviewed-only) queue.
    after = (await c.get("/api/v1/assistant/telemetry", headers=h)).json()["entries"]
    assert all(e["id"] != eid for e in after)

    # And it comes back when unreviewedOnly=false.
    all_entries = (await c.get(
        "/api/v1/assistant/telemetry?unreviewedOnly=false", headers=h,
    )).json()["entries"]
    rev = next(e for e in all_entries if e["id"] == eid)
    assert rev["assignedIntent"] == "help"
    assert rev["synonymNote"].startswith("map 'away day'")
    assert rev["reviewedAt"] is not None


@pytest.mark.asyncio
async def test_no_anthropic_left_in_assistant_module():
    """CB-C — every LLM reference should be gone from the assistant module tree."""
    import pkgutil
    from app.modules import assistant as pkg
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        src_path = f"{pkg.__path__[0]}/{mod_info.name}.py"
        try:
            with open(src_path, encoding="utf-8") as fh:
                src = fh.read().lower()
        except FileNotFoundError:
            continue
        assert "anthropic" not in src, f"anthropic reference left in {src_path}"
        assert "asyncanthropic" not in src, f"anthropic client left in {src_path}"
