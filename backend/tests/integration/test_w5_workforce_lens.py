"""W5 — Workforce lens on institution-wide supervisor capacity."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.models import Programme, Student
from app.modules.supervision.constants import SupervisionStatus, SupervisorRole
from app.modules.supervision.models import SupervisorRelationship
from app.modules.supervision.w2_models import (
    AssignmentRequestState,
    SupervisorAvailability,
    SupervisorAssignmentRequest,
    SupervisorProfile,
)


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://",
                              connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        user = User(email="wf@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "wf@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h, sm
    app.dependency_overrides.clear()
    await eng.dispose()


async def _make_person(s, given: str) -> Person:
    p = Person(given_name=given, family_name="X", email=f"{given.lower()}@t.com")
    s.add(p); await s.flush()
    return p


async def _make_student(s, prog_id, ref: str) -> Student:
    person = await _make_person(s, f"stu_{ref}")
    stu = Student(person_id=person.id, student_ref=ref,
                  programme_id=prog_id, start_date=date.today() - timedelta(days=100),
                  status=StudentStatus.active)
    s.add(stu); await s.flush()
    return stu


@pytest.mark.asyncio
async def test_workforce_lens_captures_load_capacity_and_pending(ctx):
    """Alice: overloaded and on sabbatical. Bob: healthy, room to spare. Carol: not-accepting,
    zero caseload, has a pending assignment request."""
    c, h, sm = ctx
    today = date.today()

    async with sm() as s:
        prog = Programme(name="PhD", code="PHD-W5"); s.add(prog); await s.flush()

        alice = await _make_person(s, "Alice")
        bob = await _make_person(s, "Bob")
        carol = await _make_person(s, "Carol")

        # Alice — profile cap 2, on sabbatical NOW, 3 active supervisees → over cap.
        s.add(SupervisorProfile(
            person_id=alice.id, max_students=2,
            availability=SupervisorAvailability.available, accepting_new=True,
            sabbatical_from=today - timedelta(days=5),
            sabbatical_to=today + timedelta(days=30),
        ))
        # Bob — profile cap 5, all clear, 2 active supervisees (1 primary + 1 co).
        s.add(SupervisorProfile(
            person_id=bob.id, max_students=5,
            availability=SupervisorAvailability.available, accepting_new=True,
        ))
        # Carol — profile cap 3, not accepting new, 0 caseload.
        s.add(SupervisorProfile(
            person_id=carol.id, max_students=3,
            availability=SupervisorAvailability.available, accepting_new=False,
        ))
        await s.flush()

        # Active supervisees
        for i in range(3):
            stu = await _make_student(s, prog.id, f"A{i}")
            s.add(SupervisorRelationship(
                student_id=stu.id, supervisor_person_id=alice.id,
                role=SupervisorRole.primary, status=SupervisionStatus.assigned,
                valid_from=today - timedelta(days=90), valid_to=None,
            ))
        stu_b1 = await _make_student(s, prog.id, "B1")
        s.add(SupervisorRelationship(
            student_id=stu_b1.id, supervisor_person_id=bob.id,
            role=SupervisorRole.primary, status=SupervisionStatus.assigned,
            valid_from=today - timedelta(days=90), valid_to=None,
        ))
        stu_b2 = await _make_student(s, prog.id, "B2")
        s.add(SupervisorRelationship(
            student_id=stu_b2.id, supervisor_person_id=bob.id,
            role=SupervisorRole.co_supervisor, status=SupervisionStatus.assigned,
            valid_from=today - timedelta(days=60), valid_to=None,
        ))

        # Pending assignment request targeting Carol
        target_stu = await _make_student(s, prog.id, "TGT")
        s.add(SupervisorAssignmentRequest(
            student_id=target_stu.id, proposed_supervisor_person_id=carol.id,
            proposed_role=SupervisorRole.primary,
            state=AssignmentRequestState.requested,
        ))
        await s.commit()

    r = await c.get("/api/v1/reports/supervisor-workforce", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    totals = body["totals"]
    assert totals["supervisors"] == 3
    assert totals["overCapacity"] == 1                # Alice
    assert totals["onSabbatical"] == 1                # Alice
    assert totals["notAcceptingNew"] == 1             # Carol
    # Alice on sabbatical + Carol not-accepting = 2 unavailable
    assert totals["unavailable"] == 2
    assert totals["pendingRequests"] == 1
    assert totals["totalActiveSupervisees"] == 5      # 3 + 2 + 0
    assert totals["totalCapacity"] == 2 + 5 + 3       # 10
    assert totals["utilisationPct"] == 50.0

    by_name = {row["personName"]: row for row in body["supervisors"]}

    a = by_name["Alice X"]
    assert a["caseload"] == 3 and a["maxStudents"] == 2 and a["overCapacity"] is True
    assert a["primary"] == 3 and a["co"] == 0
    assert a["onSabbatical"] is True and a["headroom"] == -1

    b = by_name["Bob X"]
    assert b["caseload"] == 2 and b["overCapacity"] is False
    assert b["primary"] == 1 and b["co"] == 1 and b["headroom"] == 3

    car = by_name["Carol X"]
    assert car["acceptingNew"] is False and car["caseload"] == 0
    assert car["pendingRequests"] == 1

    # Overloaded row appears first.
    assert body["supervisors"][0]["personName"] == "Alice X"


@pytest.mark.asyncio
async def test_workforce_lens_empty_when_nobody_supervises(ctx):
    c, h, _ = ctx
    r = await c.get("/api/v1/reports/supervisor-workforce", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["totals"]["supervisors"] == 0
    assert body["totals"]["pendingRequests"] == 0
    assert body["totals"]["defaultCap"] > 0    # institution setting still surfaces
    assert body["supervisors"] == []


@pytest.mark.asyncio
async def test_workforce_lens_person_without_profile_uses_institution_default(ctx):
    """A supervisor who has never had a W2 profile still appears, using the setting fallback."""
    c, h, sm = ctx
    today = date.today()
    async with sm() as s:
        prog = Programme(name="PhD", code="PHD-W5B"); s.add(prog); await s.flush()
        dave = await _make_person(s, "Dave")   # no SupervisorProfile
        for i in range(2):
            stu = await _make_student(s, prog.id, f"D{i}")
            s.add(SupervisorRelationship(
                student_id=stu.id, supervisor_person_id=dave.id,
                role=SupervisorRole.primary, status=SupervisionStatus.assigned,
                valid_from=today - timedelta(days=30), valid_to=None,
            ))
        await s.commit()

    r = await c.get("/api/v1/reports/supervisor-workforce", headers=h)
    body = r.json()
    row = next(x for x in body["supervisors"] if x["personName"] == "Dave X")
    assert row["hasProfile"] is False
    assert row["caseload"] == 2
    assert row["maxStudents"] == body["totals"]["defaultCap"]
