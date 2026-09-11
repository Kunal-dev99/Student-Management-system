"""Meeting brief — end-to-end with the model forced off.

The autouse fixture points every code path at MockProvider, so the paragraph must come
from the deterministic template and the evidence must still be assembled from real
records. This is the "AI as a layer" test for the second feature.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.llm import provider as provider_mod
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.funding.constants import FundingStatus, FundingType
from app.modules.funding.models import FundingArrangement
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone, MilestoneDefinition
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student
from app.modules.supervision.constants import MeetingFormat
from app.modules.supervision.models import SupervisionMeeting


@pytest.fixture(autouse=True)
def _force_mock_provider(monkeypatch):
    monkeypatch.setattr(provider_mod, "get_provider", lambda **_: provider_mod.MockProvider())
    from app.ai import client as ai_client
    from app.modules.meeting_brief import router as brief_router
    monkeypatch.setattr(ai_client, "get_provider", lambda **_: provider_mod.MockProvider())
    monkeypatch.setattr(brief_router, "provider_is_live", lambda: False)


@pytest_asyncio.fixture
async def client_and_student():
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perm = Permission(code="student.read"); s.add(perm); await s.flush()
        role = Role(name="Supervisor"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = [perm]
        user = User(email="s@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]

        p = Person(given_name="Marcus", family_name="Bell")
        s.add(p); await s.flush()
        student = Student(
            person_id=p.id, student_ref="TEST-01", start_date=date(2022, 1, 1),
            study_mode=StudyMode.full_time, status=StudentStatus.registered,
            expected_end_date=date.today() + timedelta(days=45),  # nearing end → open flag
        )
        s.add(student); await s.flush()

        prog = Programme(name="Test PhD", code="TEST")
        s.add(prog); await s.flush()
        mdef = MilestoneDefinition(programme_id=prog.id, name="Annual review")
        s.add(mdef); await s.flush()

        # An overdue milestone → open flag + "milestone overdue" change (if updated_at
        # is recent — which it is, since the row was just inserted).
        s.add(Milestone(student_id=student.id, milestone_definition_id=mdef.id,
                        status=MilestoneStatus.overdue,
                        due_date=date.today() - timedelta(days=5)))

        # Active funding.
        s.add(FundingArrangement(
            student_id=student.id, funding_type=FundingType.research_council,
            valid_from=date(2022, 1, 1), valid_to=None, status=FundingStatus.active,
        ))

        # Prior meeting recorded 20 days ago with concrete agreed actions.
        s.add(SupervisionMeeting(
            student_id=student.id,
            met_on=date.today() - timedelta(days=20),
            format=MeetingFormat.in_person,
            notes="Discussed literature review.",
            actions="Marcus to redraft chapter 2 by end of month.",
            next_meeting_on=date.today() + timedelta(days=7),
        ))
        await s.commit()
        student_id = str(student.id)

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "s@t.com", "password": "pw"})
        c.headers.update({"Authorization": f"Bearer {r.json()['accessToken']}"})
        yield c, student_id
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_meeting_brief_end_to_end_with_model_off(client_and_student):
    client, sid = client_and_student
    payload = (await client.get(f"/api/v1/meeting-brief/{sid}")).json()

    # Provenance labels the brief as deterministic — the UI can flip the chip to grey.
    assert payload["provenance"]["source"] == "fallback"
    assert payload["modelLive"] is False

    # Deterministic evidence assembled from the fixtures above.
    assert payload["student"]["name"] == "Marcus Bell"
    assert payload["daysSinceLast"] == 20
    assert "chapter 2" in (payload["lastMeetingActions"] or "").lower()

    # An overdue milestone shows up as an open flag AND (since updated_at is recent) as a change.
    assert any("overdue" in f for f in payload["openFlags"])

    # Suggested questions reference the outstanding actions from last time — the
    # deterministic rule uses "what you agreed last time" wording.
    assert any("last time" in q.lower() for q in payload["suggestedQuestions"])
    # Questions are addressed to a person, using the student's first name.
    assert any("Marcus" in q for q in payload["suggestedQuestions"])

    # The deterministic paragraph names the student, the days-since figure, and the actions,
    # in the "colleague briefing" register (first name, addressed to you).
    p = payload["paragraph"]
    assert "Marcus" in p
    assert "20 days ago" in p
    assert "chapter 2" in p.lower()
    # No system vocabulary should leak through.
    assert "open flag" not in p.lower()
    assert "N changes" not in p


@pytest.mark.asyncio
async def test_meeting_brief_missing_student_404(client_and_student):
    client, _ = client_and_student
    fake = "00000000-0000-0000-0000-000000000000"
    r = await client.get(f"/api/v1/meeting-brief/{fake}")
    assert r.status_code == 404
