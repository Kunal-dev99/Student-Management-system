"""LC-1 — leave category on suspension lifecycle events.

Pins:
  * A suspension request accepts leave_category and it round-trips on the event out payload.
  * The category is silently ignored on non-suspension events (a mode change tagged as
    "medical" must not appear medical — the value is dropped, not applied).
  * The API rejects an unknown category with a 4xx, matching the schema-level whitelist.
  * A suspension request with no category is valid — the field is optional.
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
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.student_record.constants import ProgrammeType, StudyMode
from app.modules.student_record.models import Programme, Student


TODAY = date.today()


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        u = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True); s.add(u)
        await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]
        prog = Programme(name="PhD", code="PHD-T", programme_type=ProgrammeType.research,
                         duration_months=48)
        s.add(prog); await s.flush()
        from app.modules.person.models import Person
        p = Person(given_name="Test", family_name="Student", email="ts@example.com")
        s.add(p); await s.flush()
        student = Student(person_id=p.id, student_ref="LC-001", programme_id=prog.id,
                          start_date=TODAY - timedelta(days=100),
                          expected_end_date=TODAY + timedelta(days=1300),
                          original_expected_end_date=TODAY + timedelta(days=1300),
                          study_mode=StudyMode.full_time)
        s.add(student); await s.flush()
        student_id = str(student.id)
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h, student_id
    app.dependency_overrides.clear()
    await eng.dispose()


def _suspension_body(cat=None, **overrides):
    body = {
        "eventType": "suspension",
        "reason": "test",
        "startDate": (TODAY + timedelta(days=1)).isoformat(),
        "endDate": (TODAY + timedelta(days=30)).isoformat(),
    }
    if cat is not None:
        body["leaveCategory"] = cat
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_suspension_with_medical_category_round_trips(ctx):
    c, h, sid = ctx
    r = await c.post(f"/api/v1/students/{sid}/lifecycle-events", headers=h,
                     json=_suspension_body(cat="medical"))
    assert r.status_code == 201, r.text
    assert r.json()["leaveCategory"] == "medical"

    # And on subsequent GETs the category survives serialisation.
    r2 = await c.get(f"/api/v1/students/{sid}/lifecycle-events", headers=h)
    assert r2.status_code == 200
    events = r2.json() if isinstance(r2.json(), list) else r2.json().get("events", [])
    med = [e for e in events if e.get("leaveCategory") == "medical"]
    assert len(med) == 1


@pytest.mark.asyncio
async def test_suspension_without_category_is_valid(ctx):
    """leaveCategory is optional — a suspension without one is still a valid record."""
    c, h, sid = ctx
    r = await c.post(f"/api/v1/students/{sid}/lifecycle-events", headers=h,
                     json=_suspension_body())
    assert r.status_code == 201, r.text
    assert r.json()["leaveCategory"] is None


@pytest.mark.asyncio
async def test_unknown_category_rejected(ctx):
    c, h, sid = ctx
    r = await c.post(f"/api/v1/students/{sid}/lifecycle-events", headers=h,
                     json=_suspension_body(cat="vacation"))
    assert r.status_code in (400, 422), r.text


@pytest.mark.asyncio
async def test_category_dropped_on_non_suspension(ctx):
    """A mode_change tagged 'medical' must NOT persist that tag — it would misrepresent the
    event as a medical suspension in every downstream report."""
    c, h, sid = ctx
    r = await c.post(f"/api/v1/students/{sid}/lifecycle-events", headers=h, json={
        "eventType": "mode_change",
        "reason": "switching to PT",
        "startDate": (TODAY + timedelta(days=1)).isoformat(),
        "newMode": "part_time",
        "leaveCategory": "medical",
    })
    assert r.status_code == 201, r.text
    assert r.json()["leaveCategory"] is None
