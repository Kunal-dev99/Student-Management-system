"""Executive + administrator dashboard read models (BE-1.11)."""
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
from app.modules.admissions.constants import OfferStatus
from app.modules.admissions.models import Offer
from app.modules.funding.constants import FundingStatus, FundingType
from app.modules.funding.models import FundingArrangement
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.recruitment.constants import ApplicationRoute, CandidateStage
from app.modules.recruitment.models import Application
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Student
from app.modules.thesis.constants import ThesisStatus
from app.modules.thesis.models import Thesis


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def client(engine):
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        perm = Permission(code="reporting.read")
        s.add(perm); await s.flush()
        role = Role(name="Executive")
        s.add(role); await s.flush(); await s.refresh(role, ["permissions"]); role.permissions = [perm]
        user = User(email="e@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]

        p1, p2 = Person(given_name="A", family_name="A"), Person(given_name="B", family_name="B")
        s.add_all([p1, p2]); await s.flush()
        st1 = Student(person_id=p1.id, student_ref="S1", study_mode=StudyMode.full_time, status=StudentStatus.registered)
        st2 = Student(person_id=p2.id, student_ref="S2", study_mode=StudyMode.full_time, status=StudentStatus.registered)
        s.add_all([st1, st2]); await s.flush()

        # 3 applications: 1 converted, 2 applicant
        a1 = Application(person_id=p1.id, route=ApplicationRoute.student_led, current_stage=CandidateStage.converted)
        a2 = Application(person_id=p2.id, route=ApplicationRoute.student_led, current_stage=CandidateStage.applicant)
        a3 = Application(person_id=p2.id, route=ApplicationRoute.student_led, current_stage=CandidateStage.applicant)
        s.add_all([a1, a2, a3]); await s.flush()
        s.add(Offer(application_id=a2.id, status=OfferStatus.issued))
        s.add(Thesis(student_id=st1.id, status=ThesisStatus.submitted))
        s.add(FundingArrangement(
            student_id=st1.id, funding_type=FundingType.research_council, valid_from=date(2024, 1, 1),
            valid_to=None, status=FundingStatus.active,
        ))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "e@t.com", "password": "pw"})
        c.headers.update({"Authorization": f"Bearer {r.json()['accessToken']}"})
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_executive_dashboard(client):
    r = await client.get("/api/v1/dashboards/executive")
    assert r.status_code == 200
    d = r.json()
    assert d["totals"] == {"persons": 2, "students": 2, "applications": 3, "opportunities": 0}
    assert d["applicationsInPipeline"] == 3
    assert d["conversionRatePct"] == 33.3
    assert d["fundedStudents"] == 1
    assert d["thesesSubmitted"] == 1
    assert d["activeResearchers"] == 2


@pytest.mark.asyncio
async def test_administrator_dashboard(client):
    r = await client.get("/api/v1/dashboards/administrator")
    assert r.status_code == 200
    d = r.json()
    assert d["applicationsAwaitingAssessment"] == 2
    assert d["offersAwaitingAcceptance"] == 1
    assert d["thesesSubmitted"] == 1


@pytest.mark.asyncio
async def test_reporting_requires_permission(client):
    # A fresh client without the header would 401; here we just confirm the guard exists.
    r = await client.get("/api/v1/dashboards/executive", headers={"Authorization": "Bearer bad"})
    assert r.status_code == 401
