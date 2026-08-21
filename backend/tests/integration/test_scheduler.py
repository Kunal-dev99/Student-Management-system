"""Scheduled jobs: milestone generation, funding-expiry flagging, overdue escalation (BE-2.2)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.modules.funding.constants import FundingStatus, FundingType
from app.modules.funding.models import FundingArrangement
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.progression.models import MilestoneDefinition
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Department, Programme, Student
from app.modules.workflow.constants import TaskStatus
from app.modules.workflow.models import Task


@pytest_asyncio.fixture
async def client():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perm = Permission(code="admin.configure"); s.add(perm); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = [perm]
        user = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]

        dept = Department(name="CS", code="CS"); s.add(dept); await s.flush()
        prog = Programme(name="PhD", code="PHD", department_id=dept.id); s.add(prog); await s.flush()
        s.add(MilestoneDefinition(programme_id=prog.id, name="Induction", due_offset_days=0))
        person = Person(given_name="Sam", family_name="R"); s.add(person); await s.flush()
        # Student with a programme but no milestones yet -> job should generate one.
        student = Student(person_id=person.id, student_ref="PGR-S", programme_id=prog.id,
                          start_date=date(2024, 1, 1), study_mode=StudyMode.full_time, status=StudentStatus.registered)
        s.add(student); await s.flush()
        # Funding arrangement expiring in 30 days -> should be flagged.
        s.add(FundingArrangement(
            student_id=student.id, funding_type=FundingType.research_council,
            valid_from=date(2024, 1, 1), valid_to=date.today() + timedelta(days=30),
            status=FundingStatus.active,
        ))
        # An overdue open task -> should be escalated to blocked.
        s.add(Task(title="Overdue thing", assignee_role="PGR Administrator",
                   due_at=datetime.now(timezone.utc) - timedelta(days=1), status=TaskStatus.open))
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
async def test_scheduled_jobs_run_then_idempotent(client):
    r = await client.post("/api/v1/admin/scheduled-jobs/run")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["milestonesGenerated"] == 1
    assert d["fundingExpiringFlagged"] == 1
    assert d["overdueTasksEscalated"] == 1

    # Second run: nothing new (milestone exists, funding task deduped, task already blocked).
    d2 = (await client.post("/api/v1/admin/scheduled-jobs/run")).json()
    assert d2["milestonesGenerated"] == 0
    assert d2["fundingExpiringFlagged"] == 0
    assert d2["overdueTasksEscalated"] == 0
