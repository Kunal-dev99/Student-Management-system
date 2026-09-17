"""Dry-run preview for a candidate source+transform over the profile's cohort.

The Add/Edit-field dialog needs to answer "what will my pipe actually produce?" before saving —
so the preview endpoint exists to run the *same* resolver + transform chain that generate/
validate use, deterministically, on the first N records. This file locks the contract."""
from __future__ import annotations

from datetime import date

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
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student


async def _build_ctx(student_count: int, missing_nationality_every: int | None = None):
    """Fixture body — student_count students on a single programme. Every Nth student is given no
    nationality so the 'None appears in distinct.inputs' case has real data to lean on."""
    eng = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
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

        prog = Programme(name="PhD CS", code="PHD-CS"); s.add(prog); await s.flush()
        for i in range(student_count):
            nat = None if (missing_nationality_every and i % missing_nationality_every == 0) else "British"
            person = Person(given_name=f"P{i:03d}", family_name=f"F{i:03d}", nationality=nat)
            s.add(person); await s.flush()
            # Alternate modes so distinct.inputs has more than one non-null value.
            mode = StudyMode.full_time if i % 2 == 0 else StudyMode.part_time
            s.add(Student(person_id=person.id, student_ref=f"ICR-{i:04d}", programme_id=prog.id,
                          start_date=date(2026, 10, 1), expected_end_date=date(2029, 9, 30),
                          study_mode=mode, status=StudentStatus.active))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    transport = ASGITransport(app=app)
    return eng, transport


@pytest_asyncio.fixture
async def ctx():
    eng, transport = await _build_ctx(student_count=3, missing_nationality_every=None)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest_asyncio.fixture
async def big_ctx():
    """30 students — proves the sample is capped at 20 regardless of cohort size."""
    eng, transport = await _build_ctx(student_count=30, missing_nationality_every=None)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest_asyncio.fixture
async def gappy_ctx():
    """Every 2nd student has no nationality — feeds the 'None in distinct.inputs' case."""
    eng, transport = await _build_ctx(student_count=4, missing_nationality_every=2)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@t.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        yield c, h
    app.dependency_overrides.clear()
    await eng.dispose()


async def _profile(c, h):
    r = await c.post("/api/v1/report-profiles", headers=h, json={
        "code": "HESA_STUDENT", "name": "HESA Student Return", "academicYear": "2026/27"})
    assert r.status_code == 201, r.text
    return r.json()


async def _preview(c, h, pid, source, transform=None):
    body = {"sourceExpression": source, "transform": transform}
    return await c.post(f"/api/v1/report-profiles/{pid}/preview-transform", headers=h, json=body)


@pytest.mark.asyncio
async def test_happy_path_known_transform_returns_transformed_rows(ctx):
    """A known transform runs against the cohort — hesa_mode maps 'full_time' → '01', 'part_time' → '02'."""
    c, h = ctx
    p = await _profile(c, h)
    r = await _preview(c, h, p["id"], "student.mode", "hesa_mode")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sampled"] == 3
    assert body["totalRecords"] == 3
    assert body["error"] is None
    outputs_by_ref = {row["studentRef"]: row["output"] for row in body["rows"]}
    # ICR-0000 and ICR-0002 are full_time → '01'; ICR-0001 is part_time → '02'.
    assert outputs_by_ref["ICR-0000"] == "01"
    assert outputs_by_ref["ICR-0001"] == "02"
    assert set(body["distinct"]["outputs"]) == {"01", "02"}


@pytest.mark.asyncio
async def test_unknown_transform_in_chain_returns_400(ctx):
    """A bad step anywhere in the pipe is rejected as 400 — the dialog needs a plain refusal."""
    c, h = ctx
    p = await _profile(c, h)
    r = await _preview(c, h, p["id"], "student.mode", "lower|does_not_exist")
    assert r.status_code == 400, r.text
    assert "does_not_exist" in r.json()["detail"].lower() or "unknown" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_empty_transform_returns_inputs_coerced_to_string(ctx):
    """No pipe at all — output is the input coerced to string (None becomes '')."""
    c, h = ctx
    p = await _profile(c, h)
    r = await _preview(c, h, p["id"], "student.mode", None)
    assert r.status_code == 200
    body = r.json()
    for row in body["rows"]:
        expected = "" if row["input"] is None else str(row["input"])
        assert row["output"] == expected


@pytest.mark.asyncio
async def test_sample_never_exceeds_twenty_even_when_cohort_is_larger(big_ctx):
    """The preview is a cheap, stable window — 30 students in the cohort must still yield 20 sampled."""
    c, h = big_ctx
    p = await _profile(c, h)
    r = await _preview(c, h, p["id"], "student.ref", None)
    assert r.status_code == 200
    body = r.json()
    assert body["sampled"] == 20
    assert body["totalRecords"] == 30
    assert len(body["rows"]) == 20


@pytest.mark.asyncio
async def test_distinct_inputs_contains_none_when_source_missing_on_some_records(gappy_ctx):
    """Half the cohort has no nationality — the distinct.inputs list must show a JSON null so the
    dialog can flag that empties will need a default."""
    c, h = gappy_ctx
    p = await _profile(c, h)
    r = await _preview(c, h, p["id"], "person.nationality", None)
    assert r.status_code == 200
    body = r.json()
    inputs = body["distinct"]["inputs"]
    assert None in inputs        # JSON null preserved on the input side
    assert "British" in inputs
