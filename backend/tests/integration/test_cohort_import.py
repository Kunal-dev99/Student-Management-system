"""ICR G2 (slice B) — cohort CSV import.

An institution exports its accepted cohort from a separate recruitment system and uploads it here.
What must hold:
- preview writes nothing but classifies each row (create / attach / skip / error)
- an unknown programme is a row error, not a failed upload
- commit enrols the OK rows through the normal enrol path
- re-uploading the same file is idempotent on the student reference (rows skip, no duplicates)
- flexible headers: 'name' splits into given/family, aliased column titles are accepted
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
from app.modules.person.models import Person
from app.modules.student_record.models import Programme, Student


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
        user = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]
        s.add(Programme(name="MSc Clinical Oncology", code="MSC-ONC"))
        s.add(Programme(name="PhD", code="PHD"))
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
        yield c, h, sm
    app.dependency_overrides.clear()
    await eng.dispose()


GOOD_CSV = (
    "student ref,name,email,programme code,start date,mode\n"
    "ICR-100,Amara Okonkwo,amara@t.com,MSC-ONC,2026-09-01,full time\n"
    "ICR-101,Daniel Whitfield,daniel@t.com,PHD,01/10/2026,part time\n"
)


def _upload(csv_text: str, name: str = "cohort.csv"):
    return {"file": (name, csv_text.encode("utf-8"), "text/csv")}


@pytest.mark.asyncio
async def test_preview_classifies_rows_without_writing(ctx):
    c, h, sm = ctx
    r = await c.post("/api/v1/students/import/preview", headers=h, files=_upload(GOOD_CSV))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["committed"] is False
    assert body["total"] == 2
    assert body["toCreate"] == 2
    assert {row["action"] for row in body["rows"]} == {"create"}
    # Nothing was written.
    async with sm() as s:
        assert (await s.execute(select(func.count()).select_from(Student))).scalar_one() == 0


@pytest.mark.asyncio
async def test_unknown_programme_is_a_row_error(ctx):
    c, h, _ = ctx
    csv_text = "name,programme code\nJane Doe,NOPE-999\n"
    r = await c.post("/api/v1/students/import/preview", headers=h, files=_upload(csv_text))
    assert r.status_code == 200, r.text
    row = r.json()["rows"][0]
    assert row["action"] == "error"
    assert any("unknown programme" in m for m in row["messages"])


@pytest.mark.asyncio
async def test_commit_enrols_and_is_idempotent(ctx):
    c, h, sm = ctx
    first = await c.post("/api/v1/students/import/commit", headers=h, files=_upload(GOOD_CSV))
    assert first.status_code == 201, first.text
    assert first.json()["toCreate"] == 2
    async with sm() as s:
        assert (await s.execute(select(func.count()).select_from(Student))).scalar_one() == 2
        # 'name' was split into given/family.
        amara = (await s.execute(
            select(Person).where(func.lower(Person.email) == "amara@t.com")
        )).scalar_one()
        assert amara.given_name == "Amara" and amara.family_name == "Okonkwo"
        daniel_ref = (await s.execute(
            select(Student).where(Student.student_ref == "ICR-101")
        )).scalar_one()
        assert str(daniel_ref.id)

    # Re-upload the same file: every row skips, nothing duplicated.
    second = await c.post("/api/v1/students/import/commit", headers=h, files=_upload(GOOD_CSV))
    assert second.status_code == 201, second.text
    assert second.json()["skipped"] == 2
    assert second.json()["toCreate"] == 0
    async with sm() as s:
        assert (await s.execute(select(func.count()).select_from(Student))).scalar_one() == 2


@pytest.mark.asyncio
async def test_file_without_programme_column_is_rejected(ctx):
    c, h, _ = ctx
    r = await c.post("/api/v1/students/import/preview", headers=h,
                     files=_upload("name,email\nJo Bloggs,jo@t.com\n"))
    assert r.status_code == 400, r.text  # whole-file validation error (not a per-row one)
