"""Statutory export jobs (BE-2.8, arch §13.4)."""
from __future__ import annotations

from datetime import date

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
from app.modules.student_record.models import Department, Programme, Student


@pytest_asyncio.fixture
async def client():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perm = Permission(code="reporting.read"); s.add(perm); await s.flush()
        role = Role(name="Executive"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = [perm]
        user = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]
        dept = Department(name="CS", code="CS"); s.add(dept); await s.flush()
        prog = Programme(name="PhD", code="PHD", department_id=dept.id); s.add(prog); await s.flush()
        person = Person(given_name="Ann", family_name="Lee", nationality="British"); s.add(person); await s.flush()
        s.add(Student(person_id=person.id, student_ref="PGR-1", programme_id=prog.id, start_date=date(2024, 1, 1),
                      study_mode=StudyMode.full_time, status=StudentStatus.registered))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        c.headers.update({"Authorization": f"Bearer {r.json()['accessToken']}"})
        yield c
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_statutory_export_runs_and_downloads(client):
    r = await client.post("/api/v1/exports", json={"kind": "students_statutory"})
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "complete"
    assert job["rowCount"] == 1

    assert (await client.get(f"/api/v1/exports/{job['id']}")).json()["status"] == "complete"

    dl = await client.get(f"/api/v1/exports/{job['id']}/download")
    assert dl.status_code == 200
    assert "text/csv" in dl.headers["content-type"]
    body = dl.text
    assert "student_ref" in body and "PGR-1" in body and "Ann" in body


@pytest.mark.asyncio
async def test_unknown_export_kind_rejected(client):
    r = await client.post("/api/v1/exports", json={"kind": "nope"})
    assert r.status_code == 400
