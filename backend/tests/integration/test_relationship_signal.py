"""Relationship signal — model-off proof with keyword fallback."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

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
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.portal.models import PortalMessage
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Student
from app.modules.supervision.constants import SupervisorRole, MeetingFormat
from app.modules.supervision.models import SupervisionMeeting, SupervisorRelationship


@pytest.fixture(autouse=True)
def _force_mock_provider(monkeypatch):
    monkeypatch.setattr(provider_mod, "get_provider", lambda **_: provider_mod.MockProvider())
    from app.ai import client as ai_client
    monkeypatch.setattr(ai_client, "get_provider", lambda **_: provider_mod.MockProvider())


@pytest_asyncio.fixture
async def client_and_ids():
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

        # Supervisor
        sup_person = Person(given_name="Elena", family_name="Ford", email="elena@example.com")
        s.add(sup_person); await s.flush()
        sup_user = User(email="elena@example.com", password_hash=hash_password("pw"),
                        is_active=True, person_id=sup_person.id)
        s.add(sup_user); await s.flush()
        await s.refresh(sup_user, ["roles"]); sup_user.roles = [role]

        # Student
        stu_person = Person(given_name="Marcus", family_name="Bell", email="marcus@example.com")
        s.add(stu_person); await s.flush()
        stu_user = User(email="marcus@example.com", password_hash=hash_password("pw"),
                        is_active=True, person_id=stu_person.id)
        s.add(stu_user); await s.flush()
        student = Student(
            person_id=stu_person.id, student_ref="M1",
            start_date=date(2024, 1, 1),
            study_mode=StudyMode.full_time, status=StudentStatus.registered,
        )
        s.add(student); await s.flush()

        # Elena supervises Marcus
        s.add(SupervisorRelationship(
            student_id=student.id, supervisor_person_id=sup_person.id,
            role=SupervisorRole.primary, valid_from=date(2024, 1, 1), valid_to=None,
        ))

        # Recent messages — one that should trigger the "drifting" keyword rule.
        s.add(PortalMessage(
            student_id=student.id, supervisor_person_id=sup_person.id,
            author_user_id=stu_user.id, author_role="student",
            body="Sorry I missed our meeting again — will send chapter next week.",
            created_at=datetime.now(timezone.utc) - timedelta(days=7),
        ))
        s.add(SupervisionMeeting(
            student_id=student.id, supervisor_person_id=sup_person.id,
            met_on=date.today() - timedelta(days=30),
            format=MeetingFormat.in_person,
            notes="Ok discussion", actions="Marcus to redraft chapter 2",
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
        r = await c.post("/api/v1/auth/login",
                         json={"email": "elena@example.com", "password": "pw"})
        c.headers.update({"Authorization": f"Bearer {r.json()['accessToken']}"})
        yield c, student_id
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_signal_with_model_off_uses_keyword_rules(client_and_ids):
    client, sid = client_and_ids
    payload = (await client.get(f"/api/v1/supervision/relationship-signal/{sid}")).json()

    # Model is forced off, so the classifier falls back to keyword rules.
    assert payload["provenance"]["source"] == "fallback"
    # "missed our meeting" matches the "drifting" keyword bucket.
    assert payload["label"] == "drifting"
    # Reasoning names the matched keyword so the supervisor can see why.
    assert "keyword" in payload["reasoning"].lower()
    # Evidence contains both the message and the meeting we planted.
    assert payload["evidenceTotals"] == {"messages": 1, "meetings": 1}
    assert len(payload["evidence"]) == 2


@pytest.mark.asyncio
async def test_signal_refused_for_student_not_in_caseload(client_and_ids):
    client, _ = client_and_ids
    fake = "00000000-0000-0000-0000-000000000000"
    r = await client.get(f"/api/v1/supervision/relationship-signal/{fake}")
    assert r.status_code == 404
