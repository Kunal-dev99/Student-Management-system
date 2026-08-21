"""Student portal + self-scoping (FE-2.1 backend, arch §12.3, §13.3)."""
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
from app.modules.progression.models import MilestoneDefinition
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Department, Programme, Student

PERMS = ["student.read", "progression.read", "funding.read"]


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = [Permission(code=c) for c in PERMS]
        s.add_all(perms); await s.flush()
        role = Role(name="Student"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = perms
        dept = Department(name="CS", code="CS"); s.add(dept); await s.flush()
        prog = Programme(name="PhD", code="PHD", department_id=dept.id); s.add(prog); await s.flush()
        s.add(MilestoneDefinition(programme_id=prog.id, name="Induction", due_offset_days=0))
        pa = Person(given_name="Me", family_name="Student", email="me@example.com")
        pb = Person(given_name="Other", family_name="Student")
        s.add_all([pa, pb]); await s.flush()
        sa = Student(person_id=pa.id, student_ref="PGR-ME", programme_id=prog.id, start_date=date(2024, 1, 1),
                     study_mode=StudyMode.full_time, status=StudentStatus.registered)
        sb = Student(person_id=pb.id, student_ref="PGR-OTHER", study_mode=StudyMode.full_time, status=StudentStatus.registered)
        s.add_all([sa, sb]); await s.flush()
        user = User(email="me@example.com", password_hash=hash_password("pw"), is_active=True, person_id=pa.id)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]
        await s.commit()
        ids = {"other": str(sb.id), "self_ref": "PGR-ME"}

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "me@example.com", "password": "pw"})
        c.headers.update({"Authorization": f"Bearer {r.json()['accessToken']}"})
        yield c, ids
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_student_sees_only_self(ctx):
    c, ids = ctx
    students = (await c.get("/api/v1/students")).json()
    assert students["page"]["total"] == 1
    assert students["data"][0]["studentRef"] == ids["self_ref"]
    # Cannot read another student
    assert (await c.get(f"/api/v1/students/{ids['other']}")).status_code == 404


@pytest.mark.asyncio
async def test_portal_journey(ctx):
    c, _ = ctx
    j = (await c.get("/api/v1/portal/journey")).json()
    assert j["linked"] is True
    assert j["student"]["studentRef"] == "PGR-ME"
    assert j["person"]["name"] == "Me Student"
    assert len(j["milestones"]) == 1  # Induction lazily generated
