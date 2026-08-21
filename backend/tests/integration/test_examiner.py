"""Examiner management: nominate + approve (BE-2.5, arch §8.10)."""
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
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Student

PERMS = ["student.read", "student.write", "person.read"]


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = [Permission(code=c) for c in PERMS]
        s.add_all(perms); await s.flush()
        role = Role(name="PGR Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = perms
        user = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]
        sp = Person(given_name="Stu", family_name="Dent")
        examiner = Person(given_name="Prof", family_name="Examiner")
        s.add_all([sp, examiner]); await s.flush()
        student = Student(person_id=sp.id, student_ref="PGR-E", study_mode=StudyMode.full_time, status=StudentStatus.registered)
        s.add(student); await s.commit()
        ids = {"student": str(student.id), "examiner": str(examiner.id)}

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        c.headers.update({"Authorization": f"Bearer {r.json()['accessToken']}"})
        yield c, ids
    app.dependency_overrides.clear()
    await eng.dispose()


async def _submitted_thesis(c, sid):
    t = (await c.post(f"/api/v1/students/{sid}/thesis/intention", json={"title": "T"})).json()
    await c.post(f"/api/v1/theses/{t['id']}/submit", json={"documentRef": "t.pdf"})
    return t["id"]


@pytest.mark.asyncio
async def test_nominate_and_approve(ctx):
    c, ids = ctx
    tid = await _submitted_thesis(c, ids["student"])
    r = await c.post(f"/api/v1/theses/{tid}/examiners", json={"examinerPersonId": ids["examiner"], "examinerType": "external"})
    assert r.status_code == 201, r.text
    nom = r.json()
    assert nom["approved"] is False and nom["examinerName"] == "Prof Examiner"

    listed = (await c.get(f"/api/v1/theses/{tid}/examiners")).json()
    assert len(listed) == 1

    r = await c.post(f"/api/v1/examiner-nominations/{nom['id']}/approve")
    assert r.status_code == 200 and r.json()["approved"] is True


@pytest.mark.asyncio
async def test_cannot_nominate_before_submit(ctx):
    c, ids = ctx
    # Intention only (not submitted)
    t = (await c.post(f"/api/v1/students/{ids['student']}/thesis/intention", json={})).json()
    r = await c.post(f"/api/v1/theses/{t['id']}/examiners", json={"examinerPersonId": ids["examiner"], "examinerType": "internal"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "workflow_error"


@pytest.mark.asyncio
async def test_no_duplicate_examiner(ctx):
    c, ids = ctx
    tid = await _submitted_thesis(c, ids["student"])
    body = {"examinerPersonId": ids["examiner"], "examinerType": "internal"}
    assert (await c.post(f"/api/v1/theses/{tid}/examiners", json=body)).status_code == 201
    assert (await c.post(f"/api/v1/theses/{tid}/examiners", json=body)).status_code == 409
