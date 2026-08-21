"""Workflow engine: triggers create tasks in the same transaction; queues are role-filtered
(BE-2.6/2.7, arch §9)."""
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
from app.modules.student_record.models import Department, Programme
from app.modules.workflow.models import Task

PERMS = ["person.read", "person.write", "recruitment.read", "recruitment.write", "student.read", "student.write"]


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = [Permission(code=c) for c in PERMS]
        s.add_all(perms); await s.flush()
        admin_role = Role(name="PGR Administrator"); sup_role = Role(name="Supervisor")
        s.add_all([admin_role, sup_role]); await s.flush()
        await s.refresh(admin_role, ["permissions"]); admin_role.permissions = perms
        await s.refresh(sup_role, ["permissions"]); sup_role.permissions = [perms[4]]  # student.read
        admin = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        sup = User(email="s@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add_all([admin, sup]); await s.flush()
        await s.refresh(admin, ["roles"]); admin.roles = [admin_role]
        await s.refresh(sup, ["roles"]); sup.roles = [sup_role]
        dept = Department(name="CS", code="CS"); s.add(dept); await s.flush()
        s.add(Programme(name="PhD", code="PHD", department_id=dept.id))
        person = Person(given_name="Sam", family_name="R"); s.add(person); await s.flush()
        s.add_all([
            Task(title="Onboard backlog", assignee_role="PGR Administrator"),
            Task(title="Review milestone", assignee_role="Supervisor"),
        ])
        await s.commit()
        pid = str(person.id)

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        async def login(email):
            r = await c.post("/api/v1/auth/login", json={"email": email, "password": "pw"})
            return {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, login, pid
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_task_queue_is_role_filtered(ctx):
    c, login, _ = ctx
    admin_h = await login("a@t.com")
    sup_h = await login("s@t.com")
    admin_titles = [t["title"] for t in (await c.get("/api/v1/tasks", headers=admin_h)).json()]
    sup_titles = [t["title"] for t in (await c.get("/api/v1/tasks", headers=sup_h)).json()]
    assert "Onboard backlog" in admin_titles and "Review milestone" not in admin_titles
    assert "Review milestone" in sup_titles and "Onboard backlog" not in sup_titles


@pytest.mark.asyncio
async def test_complete_task(ctx):
    c, login, _ = ctx
    h = await login("a@t.com")
    tasks = (await c.get("/api/v1/tasks", headers=h)).json()
    tid = next(t["id"] for t in tasks if t["title"] == "Onboard backlog")
    r = await c.post(f"/api/v1/tasks/{tid}/complete", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "done"
    # No longer in the open queue
    assert "Onboard backlog" not in [t["title"] for t in (await c.get("/api/v1/tasks", headers=h)).json()]


@pytest.mark.asyncio
async def test_offer_accept_creates_onboarding_task(ctx):
    c, login, pid = ctx
    h = await login("a@t.com")
    opp = (await c.post("/api/v1/opportunities", headers=h, json={"title": "X"})).json()
    appn = (await c.post("/api/v1/applications", headers=h, json={"personId": pid, "route": "opportunity_led", "researchOpportunityId": opp["id"]})).json()
    offer = (await c.post(f"/api/v1/applications/{appn['id']}/offer", headers=h, json={})).json()
    await c.post(f"/api/v1/offers/{offer['id']}/issue", headers=h)
    student = (await c.post(f"/api/v1/offers/{offer['id']}/accept", headers=h, json={})).json()
    # A new onboarding task for the new student appeared in the PGR Administrator queue.
    titles = [t["title"] for t in (await c.get("/api/v1/tasks", headers=h)).json()]
    assert any(student["studentRef"] in t for t in titles)
