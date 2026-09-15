"""ICR G3 — full milestone schedule up front + per-student overrides.

The demo mis-stated that milestones were per-student only; in fact MilestoneDefinition is per
programme and auto-instantiates. G3 closes the real gaps. What must hold:
- enrolling a student lays down the WHOLE schedule immediately (one milestone per definition)
- regenerating after a new definition is added instantiates the newcomer, leaves the rest
- a hand-edited (override) due date is preserved across a regeneration
- an ad-hoc milestone can be added for one student with no backing definition
- a template milestone re-dates when its definition offset changes; an override does not
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.progression.models import Milestone, MilestoneDefinition
from app.modules.student_record.models import Programme


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    ids = {}
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = list(perms.values())
        user = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]
        prog = Programme(name="PhD", code="PHD"); s.add(prog); await s.flush()
        ids["programme"] = str(prog.id)
        s.add(MilestoneDefinition(programme_id=prog.id, name="Induction", due_offset_days=30))
        s.add(MilestoneDefinition(programme_id=prog.id, name="Confirmation", due_offset_days=270))
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
        yield c, h, ids, sm
    app.dependency_overrides.clear()
    await eng.dispose()


async def _enrol(c, h, ids) -> str:
    r = await c.post("/api/v1/students/enrol", headers=h, json={
        "person": {"givenName": "Sam", "familyName": "Rao"},
        "programmeId": ids["programme"],
        "startDate": "2026-01-01",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_enrolment_lays_down_the_whole_schedule(ctx):
    c, h, ids, _ = ctx
    sid = await _enrol(c, h, ids)
    ms = (await c.get(f"/api/v1/students/{sid}/milestones", headers=h)).json()
    assert {m["name"] for m in ms} == {"Induction", "Confirmation"}
    assert all(m["origin"] == "template" for m in ms)


@pytest.mark.asyncio
async def test_regenerate_instantiates_a_newly_added_definition(ctx):
    c, h, ids, sm = ctx
    sid = await _enrol(c, h, ids)
    # Add a third definition after enrolment.
    async with sm() as s:
        s.add(MilestoneDefinition(programme_id=__import__("uuid").UUID(ids["programme"]),
                                  name="Thesis submission", due_offset_days=1000))
        await s.commit()
    regenerated = (await c.post(f"/api/v1/students/{sid}/milestones/regenerate", headers=h)).json()
    assert {m["name"] for m in regenerated} == {"Induction", "Confirmation", "Thesis submission"}


@pytest.mark.asyncio
async def test_override_due_date_survives_regeneration(ctx):
    c, h, ids, _ = ctx
    sid = await _enrol(c, h, ids)
    ms = (await c.get(f"/api/v1/students/{sid}/milestones", headers=h)).json()
    induction = next(m for m in ms if m["name"] == "Induction")

    patched = (await c.patch(f"/api/v1/milestones/{induction['id']}", headers=h,
                             json={"dueDate": "2026-05-05"})).json()
    assert patched["origin"] == "override"
    assert patched["dueDate"] == "2026-05-05"

    # Regeneration must not reset the overridden due date.
    regenerated = (await c.post(f"/api/v1/students/{sid}/milestones/regenerate", headers=h)).json()
    again = next(m for m in regenerated if m["name"] == "Induction")
    assert again["dueDate"] == "2026-05-05"
    assert again["origin"] == "override"


@pytest.mark.asyncio
async def test_add_ad_hoc_milestone(ctx):
    c, h, ids, sm = ctx
    sid = await _enrol(c, h, ids)
    r = await c.post(f"/api/v1/students/{sid}/milestones", headers=h,
                     json={"name": "Ethics approval", "dueDate": "2026-03-01"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["origin"] == "ad_hoc"
    assert body["milestoneDefinitionId"] is None
    ms = (await c.get(f"/api/v1/students/{sid}/milestones", headers=h)).json()
    assert "Ethics approval" in {m["name"] for m in ms}
    # 2 template + 1 ad-hoc.
    async with sm() as s:
        total = (await s.execute(
            select(func.count()).select_from(Milestone).where(Milestone.student_id == __import__("uuid").UUID(sid))
        )).scalar_one()
        assert total == 3


@pytest.mark.asyncio
async def test_regeneration_redates_a_plain_template_milestone(ctx):
    c, h, ids, sm = ctx
    sid = await _enrol(c, h, ids)
    # Change the Induction definition's offset from 30 -> 60 days.
    async with sm() as s:
        defn = (await s.execute(
            select(MilestoneDefinition).where(MilestoneDefinition.name == "Induction")
        )).scalar_one()
        defn.due_offset_days = 60
        await s.commit()
    regenerated = (await c.post(f"/api/v1/students/{sid}/milestones/regenerate", headers=h)).json()
    induction = next(m for m in regenerated if m["name"] == "Induction")
    assert induction["dueDate"] == "2026-03-02"  # 2026-01-01 + 60 days
