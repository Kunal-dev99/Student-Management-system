"""F2 — Person integrity: contacts, merge, subject-access export, GDPR erasure.

What must hold:
- merge rewrites every FK to person, deletes the losing row, records what it touched
- subject-access export names every row referencing the person (metadata-driven, not hardcoded)
- erasure pseudonymises the person and deletes contacts; row stays so audit / FK integrity holds
- an already-erased person cannot be merged into or re-erased
- person.gdpr permission is separate from person.write
"""
from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_session, get_read_session
from app.main import app
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)

    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()
        admin_role = Role(name="Institution Administrator"); s.add(admin_role); await s.flush()
        await s.refresh(admin_role, ["permissions"]); admin_role.permissions = list(perms.values())
        # A second role that has person.write but NOT person.gdpr — proves the split matters
        writer_role = Role(name="Writer"); s.add(writer_role); await s.flush()
        await s.refresh(writer_role, ["permissions"])
        writer_role.permissions = [perms["person.read"], perms["person.write"], perms["student.read"]]

        u_admin = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        u_writer = User(email="w@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add_all([u_admin, u_writer]); await s.flush()
        await s.refresh(u_admin, ["roles"]); u_admin.roles = [admin_role]
        await s.refresh(u_writer, ["roles"]); u_writer.roles = [writer_role]

        prog = Programme(name="PhD CS", code="PHD-CS"); s.add(prog); await s.flush()

        # Two persons that should merge into one — the losing person owns a Student row
        surviving = Person(given_name="Nina", family_name="Kaur", email="nina.kaur@example.com")
        losing = Person(given_name="Nina", family_name="Kaur", email="nina.kaur2@example.com")
        s.add_all([surviving, losing]); await s.flush()
        s.add(Student(
            person_id=losing.id, student_ref="PGR-N1", programme_id=prog.id,
            start_date=date(2026, 10, 1), expected_end_date=date(2029, 9, 30),
            study_mode=StudyMode.full_time, status=StudentStatus.active,
        ))
        # A third person left alone — nothing points at them yet
        lone = Person(given_name="Solo", family_name="One", email="solo@example.com")
        s.add(lone); await s.flush()
        await s.commit()

        ids = {
            "surviving": str(surviving.id), "losing": str(losing.id), "lone": str(lone.id),
        }

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        h_admin = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        r = await c.post("/api/v1/auth/login", json={"email": "w@t.com", "password": "pw"})
        h_writer = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h_admin, h_writer, ids
    app.dependency_overrides.clear()
    await eng.dispose()


# ------------------------------------------------------------------ contacts

@pytest.mark.asyncio
async def test_contacts_crud_round_trip(ctx):
    c, h, _hw, ids = ctx
    pid = ids["surviving"]
    r = await c.post(f"/api/v1/persons/{pid}/contacts", headers=h,
                     json={"channel": "phone", "value": "+441234567890", "label": "work"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    r = await c.get(f"/api/v1/persons/{pid}/contacts", headers=h)
    assert r.status_code == 200 and len(r.json()) == 1
    assert r.json()[0]["doNotContact"] is False

    r = await c.patch(f"/api/v1/persons/{pid}/contacts/{cid}", headers=h,
                      json={"doNotContact": True})
    assert r.status_code == 200 and r.json()["doNotContact"] is True

    r = await c.delete(f"/api/v1/persons/{pid}/contacts/{cid}", headers=h)
    assert r.status_code == 204
    r = await c.get(f"/api/v1/persons/{pid}/contacts", headers=h)
    assert r.json() == []


# ------------------------------------------------------------------ merge

@pytest.mark.asyncio
async def test_merge_rewrites_fks_and_deletes_the_loser(ctx):
    c, h, _hw, ids = ctx
    r = await c.post("/api/v1/persons/merge", headers=h, json={
        "survivingPersonId": ids["surviving"],
        "losingPersonId": ids["losing"],
        "reason": "confirmed duplicate — same person, two applicant emails",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    # The Student row referenced the loser; the merge should have rewritten it
    assert body["touched"].get("student.person_id") == 1
    assert body["totalRowsRewritten"] >= 1

    # The losing person no longer resolves
    r = await c.get(f"/api/v1/persons/{ids['losing']}", headers=h)
    assert r.status_code == 404

    # The student now belongs to the surviving person (via export)
    r = await c.get(f"/api/v1/persons/{ids['surviving']}/export", headers=h)
    assert r.status_code == 200
    refs = r.json()["related"].get("student", [])
    assert len(refs) == 1 and refs[0]["student_ref"] == "PGR-N1"


@pytest.mark.asyncio
async def test_merge_refuses_self_merge_and_missing_person(ctx):
    c, h, _hw, ids = ctx
    r = await c.post("/api/v1/persons/merge", headers=h, json={
        "survivingPersonId": ids["surviving"], "losingPersonId": ids["surviving"],
    })
    assert r.status_code == 422
    r = await c.post("/api/v1/persons/merge", headers=h, json={
        "survivingPersonId": ids["surviving"],
        "losingPersonId": "00000000-0000-0000-0000-000000000000",
    })
    assert r.status_code == 404


# ------------------------------------------------------------------ export

@pytest.mark.asyncio
async def test_export_contains_person_and_all_referencing_rows(ctx):
    c, h, _hw, ids = ctx
    # give the losing person a phone contact so the export must include that too
    await c.post(f"/api/v1/persons/{ids['losing']}/contacts", headers=h,
                 json={"channel": "phone", "value": "0800", "label": "old"})
    r = await c.get(f"/api/v1/persons/{ids['losing']}/export", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["person"]["email"] == "nina.kaur2@example.com"
    assert "student" in body["related"] and len(body["related"]["student"]) == 1
    assert "person_contact" in body["related"] and len(body["related"]["person_contact"]) == 1
    # Metadata-driven: tables list is deterministic, sorted
    tables = list(body["related"].keys())
    assert tables == sorted(tables)


# ------------------------------------------------------------------ erasure

@pytest.mark.asyncio
async def test_erase_pseudonymises_person_and_drops_contacts(ctx):
    c, h, _hw, ids = ctx
    await c.post(f"/api/v1/persons/{ids['lone']}/contacts", headers=h,
                 json={"channel": "phone", "value": "0800"})
    r = await c.post(f"/api/v1/persons/{ids['lone']}/erase", headers=h)
    assert r.status_code == 200

    r = await c.get(f"/api/v1/persons/{ids['lone']}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["givenName"] == "erased" and body["familyName"] == "erased"
    assert body["email"].startswith("erased:")

    r = await c.get(f"/api/v1/persons/{ids['lone']}/contacts", headers=h)
    assert r.json() == []


@pytest.mark.asyncio
async def test_erase_is_idempotent_and_blocks_merge(ctx):
    c, h, _hw, ids = ctx
    await c.post(f"/api/v1/persons/{ids['lone']}/erase", headers=h)
    r = await c.post(f"/api/v1/persons/{ids['lone']}/erase", headers=h)
    assert r.status_code == 409
    r = await c.post("/api/v1/persons/merge", headers=h, json={
        "survivingPersonId": ids["surviving"], "losingPersonId": ids["lone"],
    })
    assert r.status_code == 409


# ------------------------------------------------------------------ RBAC

@pytest.mark.asyncio
async def test_gdpr_endpoints_refuse_without_person_gdpr_permission(ctx):
    c, _h, h_writer, ids = ctx
    r = await c.post("/api/v1/persons/merge", headers=h_writer, json={
        "survivingPersonId": ids["surviving"], "losingPersonId": ids["losing"],
    })
    assert r.status_code == 403
    r = await c.get(f"/api/v1/persons/{ids['lone']}/export", headers=h_writer)
    assert r.status_code == 403
    r = await c.post(f"/api/v1/persons/{ids['lone']}/erase", headers=h_writer)
    assert r.status_code == 403
