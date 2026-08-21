"""Phase 4A — 'make it real' features:
documents (upload/download/scope), auth hardening (lockout/logout/reset), audit trail,
notification preferences, and outbox retry -> dead-letter -> replay.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Student


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    ids = {}
    async with sm() as s:
        perms = {code: Permission(code=code) for code in PERMISSIONS}
        for p in perms.values():
            s.add(p)
        await s.flush()
        admin_role = Role(name="Institution Administrator"); s.add(admin_role); await s.flush()
        await s.refresh(admin_role, ["permissions"]); admin_role.permissions = list(perms.values())
        sup_role = Role(name="Supervisor"); s.add(sup_role); await s.flush()
        await s.refresh(sup_role, ["permissions"])
        sup_role.permissions = [perms["student.read"], perms["document.read"]]

        admin = User(email="admin@t.com", password_hash=hash_password("admin123"), is_active=True)
        s.add(admin); await s.flush(); await s.refresh(admin, ["roles"]); admin.roles = [admin_role]

        sup_person = Person(given_name="Sue", family_name="Super")
        s.add(sup_person); await s.flush()
        sup = User(email="sup@t.com", password_hash=hash_password("super123"), is_active=True, person_id=sup_person.id)
        s.add(sup); await s.flush(); await s.refresh(sup, ["roles"]); sup.roles = [sup_role]

        person = Person(given_name="Stu", family_name="Dent"); s.add(person); await s.flush()
        student = Student(person_id=person.id, student_ref="PGR-X", start_date=date(2024, 1, 1),
                          study_mode=StudyMode.full_time, status=StudentStatus.registered)
        s.add(student); await s.flush()
        ids["student_id"] = str(student.id)
        await s.commit()

    async def _get_session():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, sm, ids
    app.dependency_overrides.clear()
    await eng.dispose()


async def _login(c, email, pw):
    r = await c.post("/api/v1/auth/login", json={"email": email, "password": pw})
    return r


async def _token(c, email="admin@t.com", pw="admin123"):
    r = await _login(c, email, pw)
    return r.json()["accessToken"]


@pytest.mark.asyncio
async def test_document_upload_download_and_scope(ctx):
    c, sm, ids = ctx
    tok = await _token(c)
    h = {"Authorization": f"Bearer {tok}"}
    content = b"%PDF-1.4 fake thesis bytes\n0123456789"
    files = {"file": ("thesis.pdf", content, "application/pdf")}
    data = {"ownerType": "student", "ownerId": ids["student_id"], "docType": "thesis"}
    up = await c.post("/api/v1/documents", data=data, files=files, headers=h)
    assert up.status_code == 201, up.text
    doc_id = up.json()["id"]

    lst = await c.get(f"/api/v1/documents?ownerType=student&ownerId={ids['student_id']}", headers=h)
    assert len(lst.json()) == 1

    dl = await c.get(f"/api/v1/documents/{doc_id}/download", headers=h)
    assert dl.status_code == 200
    assert dl.content == content  # byte-identical round-trip

    # Supervisor with no supervisees is out of scope for this student's documents -> 403.
    stok = await _token(c, "sup@t.com", "super123")
    sh = {"Authorization": f"Bearer {stok}"}
    denied = await c.get(f"/api/v1/documents?ownerType=student&ownerId={ids['student_id']}", headers=sh)
    assert denied.status_code == 403

    d = await c.delete(f"/api/v1/documents/{doc_id}", headers=h)
    assert d.status_code == 204


@pytest.mark.asyncio
async def test_account_lockout(ctx):
    c, sm, ids = ctx
    for _ in range(5):
        r = await _login(c, "admin@t.com", "wrong")
        assert r.status_code == 401
    # Now locked even with the correct password.
    r = await _login(c, "admin@t.com", "admin123")
    assert r.status_code == 401
    assert "locked" in r.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_logout_revokes_refresh(ctx):
    c, sm, ids = ctx
    login = (await _login(c, "admin@t.com", "admin123")).json()
    refresh = login["refreshToken"]
    # refresh works once
    r1 = await c.post("/api/v1/auth/refresh", json={"refreshToken": refresh})
    assert r1.status_code == 200
    new_refresh = r1.json()["refreshToken"]
    # logout revokes the (rotated) refresh token
    out = await c.post("/api/v1/auth/logout", json={"refreshToken": new_refresh})
    assert out.status_code == 200
    r2 = await c.post("/api/v1/auth/refresh", json={"refreshToken": new_refresh})
    assert r2.status_code == 401  # revoked


@pytest.mark.asyncio
async def test_password_reset_cycle(ctx, monkeypatch):
    c, sm, ids = ctx
    captured = {}

    async def fake_send(*, to, subject, body):
        captured["body"] = body

    monkeypatch.setattr("app.modules.identity.service.send_email", fake_send)
    req = await c.post("/api/v1/auth/password-reset/request", json={"email": "admin@t.com"})
    assert req.status_code == 200
    token = captured["body"].split("token=")[1].strip()
    conf = await c.post("/api/v1/auth/password-reset/confirm", json={"token": token, "newPassword": "newpass123"})
    assert conf.status_code == 200
    # old password rejected, new one works
    assert (await _login(c, "admin@t.com", "admin123")).status_code == 401
    assert (await _login(c, "admin@t.com", "newpass123")).status_code == 200


@pytest.mark.asyncio
async def test_audit_trail_records_mutations(ctx):
    c, sm, ids = ctx
    tok = await _token(c)
    h = {"Authorization": f"Bearer {tok}"}
    # a mutating request
    await c.patch(f"/api/v1/students/{ids['student_id']}", json={"status": "active"}, headers=h)
    audit = await c.get(f"/api/v1/audit?entityType=student&entityId={ids['student_id']}", headers=h)
    assert audit.status_code == 200
    rows = audit.json()
    assert any(r["method"] == "PATCH" and r["actorEmail"] == "admin@t.com" for r in rows)


@pytest.mark.asyncio
async def test_notification_preferences(ctx):
    c, sm, ids = ctx
    tok = await _token(c)
    h = {"Authorization": f"Bearer {tok}"}
    default = await c.get("/api/v1/notifications/preferences", headers=h)
    assert default.json()["emailEnabled"] is True
    upd = await c.put("/api/v1/notifications/preferences", headers=h,
                      json={"emailEnabled": False, "digest": True, "mutedEvents": ["milestone.decided"]})
    assert upd.json()["emailEnabled"] is False
    assert upd.json()["mutedEvents"] == ["milestone.decided"]


@pytest.mark.asyncio
async def test_outbox_retry_deadletter_replay(ctx, monkeypatch):
    c, sm, ids = ctx
    from app.modules.workflow.models import OutboxEvent
    import app.modules.integration.service as isvc

    # Seed an outbox event that routes to the finance adapter.
    async with sm() as s:
        ev = OutboxEvent(aggregate_type="funding_arrangement", aggregate_id=None or __import__("uuid").uuid4(),
                         event_type="funding.changed", payload={"x": 1}, created_at=datetime.now(timezone.utc))
        s.add(ev); await s.commit(); ev_id = str(ev.id)

    async def failing_deliver(adapter, event_type, payload):
        raise RuntimeError("partner down")

    monkeypatch.setattr(isvc, "deliver", failing_deliver)
    tok = await _token(c)
    h = {"Authorization": f"Bearer {tok}"}
    # Dispatch repeatedly; backoff sets next_attempt_at in the future, so clear it each round.
    last = None
    for _ in range(5):
        last = (await c.post("/api/v1/integration/dispatch", headers=h)).json()
        async with sm() as s:
            row = await s.get(OutboxEvent, __import__("uuid").UUID(ev_id))
            row.next_attempt_at = None
            await s.commit()
    async with sm() as s:
        row = await s.get(OutboxEvent, __import__("uuid").UUID(ev_id))
        assert row.dead_lettered is True
        assert row.attempts >= 5

    # Replay resets it.
    rp = await c.post(f"/api/v1/integration/dead-letters/{ev_id}/replay", headers=h)
    assert rp.json()["data"]["replayed"] is True
    async with sm() as s:
        row = await s.get(OutboxEvent, __import__("uuid").UUID(ev_id))
        assert row.dead_lettered is False and row.attempts == 0
