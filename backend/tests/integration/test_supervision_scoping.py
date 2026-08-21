"""Supervision + row-scoping (BE-1.6, BE-1.0b).

Security assertion (arch §12.3): a supervisor sees only students they currently supervise;
a broad role sees all. Scoping is enforced at the query layer, not the client.
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
from app.db.session import get_session
from app.main import app
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Student
from app.modules.supervision.constants import SupervisionStatus, SupervisorRole
from app.modules.supervision.models import SupervisorRelationship


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def ctx(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        perms = {c: Permission(code=c) for c in ("student.read", "student.write", "person.read")}
        s.add_all(perms.values())
        await s.flush()

        role_admin = Role(name="PGR Administrator")   # unrestricted (sees all)
        role_sup = Role(name="Supervisor")            # scoped to own supervisees
        s.add_all([role_admin, role_sup])
        await s.flush()
        await s.refresh(role_admin, ["permissions"]); role_admin.permissions = list(perms.values())
        await s.refresh(role_sup, ["permissions"]); role_sup.permissions = [perms["student.read"], perms["person.read"]]

        elena = Person(given_name="Elena", family_name="Ford")
        person_a = Person(given_name="Ann", family_name="A")
        person_b = Person(given_name="Ben", family_name="B")
        s.add_all([elena, person_a, person_b])
        await s.flush()

        admin = User(email="admin@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(admin); await s.flush(); await s.refresh(admin, ["roles"]); admin.roles = [role_admin]
        sup = User(email="sup@t.com", password_hash=hash_password("pw"), is_active=True, person_id=elena.id)
        s.add(sup); await s.flush(); await s.refresh(sup, ["roles"]); sup.roles = [role_sup]

        student_a = Student(person_id=person_a.id, student_ref="PGR-A", study_mode=StudyMode.full_time, status=StudentStatus.registered)
        student_b = Student(person_id=person_b.id, student_ref="PGR-B", study_mode=StudyMode.full_time, status=StudentStatus.registered)
        s.add_all([student_a, student_b])
        await s.flush()
        s.add(SupervisorRelationship(
            student_id=student_a.id, supervisor_person_id=elena.id,
            role=SupervisorRole.primary, status=SupervisionStatus.active, valid_from=date(2025, 1, 1),
        ))
        await s.commit()
        ids = {"a": str(student_a.id), "b": str(student_b.id), "elena": str(elena.id)}

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async def token(email):
            r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw"})
            return {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield client, token, ids
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_sees_all_students(ctx):
    client, token, _ = ctx
    h = await token("admin@t.com")
    r = await client.get("/api/v1/students", headers=h)
    assert r.status_code == 200
    assert r.json()["page"]["total"] == 2


@pytest.mark.asyncio
async def test_supervisor_sees_only_supervisees(ctx):
    client, token, ids = ctx
    h = await token("sup@t.com")
    r = await client.get("/api/v1/students", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["page"]["total"] == 1
    assert data["data"][0]["id"] == ids["a"]


@pytest.mark.asyncio
async def test_supervisor_cannot_read_other_student(ctx):
    client, token, ids = ctx
    h = await token("sup@t.com")
    # Own student -> ok
    assert (await client.get(f"/api/v1/students/{ids['a']}", headers=h)).status_code == 200
    # Someone else's student -> 404 (out of scope, not 403, per arch §12.3)
    r = await client.get(f"/api/v1/students/{ids['b']}", headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_assign_and_end_supervisor(ctx):
    client, token, ids = ctx
    h = await token("admin@t.com")
    # Assign Elena to student_b as well
    r = await client.post(
        f"/api/v1/students/{ids['b']}/supervisors", headers=h,
        json={"supervisorPersonId": ids["elena"], "role": "primary"},
    )
    assert r.status_code == 201, r.text
    rel_id = r.json()["id"]
    # Now the supervisor sees BOTH students
    hs = await token("sup@t.com")
    assert (await client.get("/api/v1/students", headers=hs)).json()["page"]["total"] == 2
    # End the new relationship -> supervisor back to one
    r = await client.post(f"/api/v1/supervisors/{rel_id}/end", headers=h)
    assert r.status_code == 200 and r.json()["validTo"] is not None
    assert (await client.get("/api/v1/students", headers=hs)).json()["page"]["total"] == 1
