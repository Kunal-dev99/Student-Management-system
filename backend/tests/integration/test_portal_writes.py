"""Student portal write endpoints — confirm meeting, declare intent to submit.

Scoping is the whole point of these tests: a student can only act on records tied to
their own person record. Anything else is a 404, never a 403 (which would leak that
another student's data exists).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Student
from app.modules.supervision.constants import MeetingFormat
from app.modules.supervision.models import SupervisionMeeting


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
        # A "student" role with the minimum needed permissions.
        perm = Permission(code="student.self")
        s.add(perm); await s.flush()
        role = Role(name="Student"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = [perm]

        # Two persons, two students, two users — a student for each so we can prove
        # cross-student isolation.
        alice_p = Person(given_name="Alice", family_name="Alpha", email="alice@t.com")
        bob_p = Person(given_name="Bob", family_name="Beta", email="bob@t.com")
        s.add_all([alice_p, bob_p]); await s.flush()

        alice_s = Student(
            person_id=alice_p.id, student_ref="A1",
            start_date=date(2024, 1, 1), study_mode=StudyMode.full_time,
            status=StudentStatus.registered,
        )
        bob_s = Student(
            person_id=bob_p.id, student_ref="B1",
            start_date=date(2024, 1, 1), study_mode=StudyMode.full_time,
            status=StudentStatus.registered,
        )
        s.add_all([alice_s, bob_s]); await s.flush()

        alice_user = User(
            email="alice@t.com", password_hash=hash_password("pw"),
            is_active=True, person_id=alice_p.id,
        )
        s.add(alice_user); await s.flush()
        await s.refresh(alice_user, ["roles"]); alice_user.roles = [role]

        # Two meetings — one for Alice, one for Bob.
        alice_meeting = SupervisionMeeting(
            student_id=alice_s.id,
            met_on=date.today() - timedelta(days=5),
            format=MeetingFormat.in_person,
            notes="Discussed ch2.",
            actions="Redraft by end of month.",
        )
        bob_meeting = SupervisionMeeting(
            student_id=bob_s.id,
            met_on=date.today() - timedelta(days=3),
            format=MeetingFormat.in_person,
            notes="Bob's meeting.",
            actions="Bob's actions.",
        )
        s.add_all([alice_meeting, bob_meeting])
        await s.commit()

        alice_meeting_id = str(alice_meeting.id)
        bob_meeting_id = str(bob_meeting.id)

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "alice@t.com", "password": "pw"})
        c.headers.update({"Authorization": f"Bearer {r.json()['accessToken']}"})
        yield c, alice_meeting_id, bob_meeting_id
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_student_can_confirm_their_own_meeting(client_and_ids):
    client, alice_meeting_id, _ = client_and_ids
    r = await client.post(f"/api/v1/portal/meetings/{alice_meeting_id}/confirm")
    assert r.status_code == 200
    body = r.json()
    assert body["studentConfirmed"] is True


@pytest.mark.asyncio
async def test_student_cannot_confirm_another_students_meeting(client_and_ids):
    """Bob's meeting is invisible to Alice — 404, never 403."""
    client, _, bob_meeting_id = client_and_ids
    r = await client.post(f"/api/v1/portal/meetings/{bob_meeting_id}/confirm")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_student_can_declare_intent_to_submit(client_and_ids):
    client, _, _ = client_and_ids
    r = await client.post(
        "/api/v1/portal/thesis/intent-to-submit",
        json={"title": "A working title"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "intention_to_submit"
    assert body["title"] == "A working title"
    assert body["intentionAt"] is not None


@pytest.mark.asyncio
async def test_student_can_declare_intent_without_title(client_and_ids):
    client, _, _ = client_and_ids
    r = await client.post("/api/v1/portal/thesis/intent-to-submit", json={"title": None})
    assert r.status_code == 200
