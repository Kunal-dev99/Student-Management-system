"""Phase 3 analytics: PGR Enterprise 360 + risk/completion (BE-3.1/3.2)."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.completion.constants import CompletionStatus
from app.modules.completion.models import Completion
from app.modules.funding.constants import FundingStatus, FundingType
from app.modules.funding.models import FundingArrangement
from app.modules.identity.models import Permission, Role, User
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.models import Person, PersonRelationship
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Student


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

        pa = Person(given_name="A", family_name="A", nationality="British")
        pb = Person(given_name="B", family_name="B")
        pc = Person(given_name="C", family_name="C")
        s.add_all([pa, pb, pc]); await s.flush()
        # A: registered, funded, also an employee
        s.add(PersonRelationship(person_id=pa.id, relationship_type=PersonRelationshipType.employee, valid_from=date(2024, 1, 1), valid_to=None))
        sa = Student(person_id=pa.id, student_ref="A1", start_date=date(2022, 1, 1), study_mode=StudyMode.full_time, status=StudentStatus.registered)
        sb = Student(person_id=pb.id, student_ref="B1", start_date=date(2023, 1, 1), study_mode=StudyMode.full_time, status=StudentStatus.registered)
        sc = Student(person_id=pc.id, student_ref="C1", start_date=date(2020, 1, 1), study_mode=StudyMode.full_time, status=StudentStatus.completed)
        s.add_all([sa, sb, sc]); await s.flush()
        s.add(FundingArrangement(student_id=sa.id, funding_type=FundingType.research_council, valid_from=date(2022, 1, 1), valid_to=None, status=FundingStatus.active))
        s.add(Completion(student_id=sc.id, status=CompletionStatus.graduated, graduation_date=date(2024, 1, 1)))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        c.headers.update({"Authorization": f"Bearer {r.json()['accessToken']}"})
        yield c
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_enterprise_360_five_lenses(client):
    d = (await client.get("/api/v1/reports/pgr-enterprise-360")).json()
    assert d["summary"]["population"] == 3
    assert d["summary"]["funded"] == 1
    assert d["summary"]["employees"] == 1
    assert set(d["lenses"]) == {"student", "research", "funding", "workforce", "statutory"}
    row = d["population"][0]
    assert set(row.keys()) >= {"student", "research", "funding", "workforce", "statutory"}


@pytest.mark.asyncio
async def test_analytics_risk_and_completion(client):
    d = (await client.get("/api/v1/reports/analytics")).json()
    # B is active with no funding -> at risk; A is funded.
    assert d["risk"]["atRiskCount"] == 1
    assert d["risk"]["activeStudents"] == 2
    # 1 of 3 students completed.
    assert d["completion"]["completed"] == 1
    assert d["completion"]["completionRatePct"] == 33.3
    # completion took 2020-01-01 -> 2024-01-01
    assert d["completion"]["avgTimeToCompletionDays"] is not None
    assert d["forecast"]["onTrack"] == 1
