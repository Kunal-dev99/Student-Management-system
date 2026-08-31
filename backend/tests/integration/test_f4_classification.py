"""F4 — Award classification workflow + certificate PDF.

What must hold:
- propose (draft → proposed) creates the Award row if none, refuses unknown classification
- confirm (proposed → confirmed) enforces approver separation — the confirmer differs from the proposer
- publish (confirmed → published) renders a real PDF and attaches it as a Document
- graduation is refused unless the award is published
- download returns the stored PDF bytes
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
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Student


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
        u1 = User(email="chair@t.com", password_hash=hash_password("pw"), is_active=True)
        u2 = User(email="board@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add_all([u1, u2]); await s.flush()
        await s.refresh(u1, ["roles"]); u1.roles = [role]
        await s.refresh(u2, ["roles"]); u2.roles = [role]

        person = Person(given_name="Rae", family_name="Ito")
        s.add(person); await s.flush()
        student = Student(person_id=person.id, student_ref="PGR-F4",
                          study_mode=StudyMode.full_time, status=StudentStatus.registered)
        s.add(student); await s.flush()
        await s.commit()
        ids = {"student": str(student.id)}

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        h_chair = {"Authorization": f"Bearer {(await c.post('/api/v1/auth/login', json={'email': 'chair@t.com', 'password': 'pw'})).json()['accessToken']}"}
        h_board = {"Authorization": f"Bearer {(await c.post('/api/v1/auth/login', json={'email': 'board@t.com', 'password': 'pw'})).json()['accessToken']}"}
        yield c, h_chair, h_board, ids
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_propose_creates_award_and_moves_to_proposed(ctx):
    c, h_chair, _h, ids = ctx
    r = await c.post(f"/api/v1/students/{ids['student']}/classification/propose", headers=h_chair,
                     json={"classification": "PhD"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["classification"] == "PhD"
    assert body["classificationState"] == "proposed"


@pytest.mark.asyncio
async def test_unknown_classification_refused(ctx):
    c, h_chair, _h, ids = ctx
    r = await c.post(f"/api/v1/students/{ids['student']}/classification/propose", headers=h_chair,
                     json={"classification": "NotARealDegree"})
    assert r.status_code == 422 and "unknown" in r.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_confirm_enforces_approver_separation(ctx):
    c, h_chair, h_board, ids = ctx
    await c.post(f"/api/v1/students/{ids['student']}/classification/propose", headers=h_chair,
                 json={"classification": "PhD"})
    # Same actor confirming their own proposal is refused
    r = await c.post(f"/api/v1/students/{ids['student']}/classification/confirm", headers=h_chair)
    assert r.status_code == 422 and "separation" in r.json()["error"]["message"].lower()
    # A different actor confirms → OK
    r = await c.post(f"/api/v1/students/{ids['student']}/classification/confirm", headers=h_board)
    assert r.status_code == 200 and r.json()["classificationState"] == "confirmed"


@pytest.mark.asyncio
async def test_publish_renders_certificate_pdf_and_download_works(ctx):
    c, h_chair, h_board, ids = ctx
    await c.post(f"/api/v1/students/{ids['student']}/classification/propose", headers=h_chair,
                 json={"classification": "PhD"})
    await c.post(f"/api/v1/students/{ids['student']}/classification/confirm", headers=h_board)
    r = await c.post(f"/api/v1/students/{ids['student']}/classification/publish", headers=h_chair)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["classificationState"] == "published"
    assert body["certificateDocumentId"] and body["certificateFilename"].endswith(".pdf")

    # Download the certificate — real PDF bytes, non-empty, PDF header
    r = await c.get(f"/api/v1/students/{ids['student']}/certificate", headers=h_chair)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1000


@pytest.mark.asyncio
async def test_publish_refuses_without_confirmed_state(ctx):
    c, h_chair, _h, ids = ctx
    r = await c.post(f"/api/v1/students/{ids['student']}/classification/publish", headers=h_chair)
    assert r.status_code == 404  # no award yet
    await c.post(f"/api/v1/students/{ids['student']}/classification/propose", headers=h_chair,
                 json={"classification": "PhD"})
    r = await c.post(f"/api/v1/students/{ids['student']}/classification/publish", headers=h_chair)
    assert r.status_code == 422  # proposed, not confirmed
