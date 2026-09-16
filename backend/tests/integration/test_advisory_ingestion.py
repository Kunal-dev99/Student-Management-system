"""ICR G5 — statutory advisory ingestion (ingest → recommend → Registry accepts).

Drives the real endpoints: paste an advisory as directives, get a deterministic diff, then have a
Registry owner accept it — and prove the accepted version supersedes the code baseline everywhere
(the /specs picker, from-spec pre-mapping, and the compile gate) while reject leaves the baseline
untouched. The AI extraction path is deliberately not exercised (model off → deterministic core).
"""
from __future__ import annotations

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


BASE_CODE = "HESA_STUDENT"
BASE_KEY = "HESA_STUDENT:2026/27"


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
        u = User(email="a@t.com", password_hash=hash_password("pw"), is_active=True)
        s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [role]
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
        yield c, h
    app.dependency_overrides.clear()
    await eng.dispose()


ADVISORY = """
YEAR: 2027/28
# 2027/28 HESA changes
ADD FIELD SEXORT "Sexual orientation" coding=[10,11,12,13,98] keyed_at="Person › sexual orientation"
REMOVE FIELD TERMTIME
CODING MODE = [01,02,03,31,99]
DESC STULOAD "Student instance load (FTE, revised 2027/28)"
RULE format_yyyymmdd BIRTHDTE "must be a valid date"
"""


async def _ingest(c, h, text=ADVISORY, year=None):
    body = {"packCode": BASE_CODE, "rawText": text}
    if year:
        body["academicYear"] = year
    r = await c.post("/api/v1/report-advisories/ingest", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_ingest_produces_a_deterministic_diff(ctx):
    c, h = ctx
    adv = await _ingest(c, h)
    assert adv["academicYear"] == "2027/28"
    assert adv["status"] == "ingested"
    assert adv["parseSource"] == "directive"
    kinds = {ch["type"] for ch in adv["changes"]}
    assert kinds == {
        "field_added", "field_removed", "coding_changed", "description_changed", "rule_added",
    }
    # The added field is present in the proposed pack, the removed one is gone.
    proposed = {f["field"] for f in adv["proposedFields"]}
    assert "SEXORT" in proposed and "TERMTIME" not in proposed
    # A coding_changed entry carries before → after coding frames.
    coding = next(ch for ch in adv["changes"] if ch["type"] == "coding_changed")
    assert coding["field"] == "MODE" and "99" in coding["after"] and "99" not in (coding["before"] or [])


@pytest.mark.asyncio
async def test_accept_supersedes_the_baseline_everywhere(ctx):
    c, h = ctx
    adv = await _ingest(c, h)

    acc = await c.post(f"/api/v1/report-advisories/{adv['id']}/accept", headers=h,
                       json={"note": "Approved for 2027/28"})
    assert acc.status_code == 200, acc.text
    version = acc.json()
    assert version["status"] == "active" and version["academicYear"] == "2027/28"
    assert version["version"] == 2

    # The picker now lists the accepted 2027/28 version alongside the baseline.
    specs = (await c.get("/api/v1/report-profiles/specs", headers=h)).json()["specs"]
    keys = {s["key"] for s in specs}
    assert "HESA_STUDENT:2027/28" in keys and BASE_KEY in keys

    # from-spec on the new key pre-maps the *advisory* field set: SEXORT in, TERMTIME out.
    prof = await c.post("/api/v1/report-profiles/from-spec", headers=h,
                        json={"specKey": "HESA_STUDENT:2027/28"})
    assert prof.status_code == 201, prof.text
    fields = {m["targetField"] for m in prof.json()["fields"]}
    assert "SEXORT" in fields and "TERMTIME" not in fields

    # The advisory is now marked accepted.
    got = (await c.get(f"/api/v1/report-advisories/{adv['id']}", headers=h)).json()
    assert got["status"] == "accepted"


@pytest.mark.asyncio
async def test_reject_leaves_the_baseline_untouched(ctx):
    c, h = ctx
    adv = await _ingest(c, h)
    rej = await c.post(f"/api/v1/report-advisories/{adv['id']}/reject", headers=h,
                       json={"note": "Not this year"})
    assert rej.status_code == 200, rej.text
    assert rej.json()["status"] == "rejected"

    # No new active version — the picker still only has the baseline year.
    specs = (await c.get("/api/v1/report-profiles/specs", headers=h)).json()["specs"]
    keys = {s["key"] for s in specs}
    assert keys == {BASE_KEY}

    # A second accept attempt is refused (already decided).
    acc = await c.post(f"/api/v1/report-advisories/{adv['id']}/accept", headers=h, json={})
    assert acc.status_code == 400


@pytest.mark.asyncio
async def test_unknown_directive_becomes_a_warning_not_a_change(ctx):
    c, h = ctx
    adv = await _ingest(c, h, text="YEAR: 2027/28\nFROBNICATE THE WIDGET\nREMOVE FIELD TERMTIME\n")
    assert [ch["type"] for ch in adv["changes"]] == ["field_removed"]
    assert any("unrecognised directive" in w for w in adv["parseWarnings"])


@pytest.mark.asyncio
async def test_ingest_without_a_year_is_rejected(ctx):
    c, h = ctx
    r = await c.post("/api/v1/report-advisories/ingest", headers=h,
                     json={"packCode": BASE_CODE, "rawText": "REMOVE FIELD TERMTIME\n"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_assisted_ingest_from_uploaded_file(ctx):
    c, h = ctx
    content = b"YEAR: 2030/31\nREMOVE FIELD TERMTIME\nADD FIELD FOO \"bar\" coding=[1,2]\n"
    r = await c.post(
        "/api/v1/report-advisories/ingest-upload", headers=h,
        files={"file": ("advisory.txt", content, "text/plain")},
        data={"packCode": BASE_CODE, "academicYear": "2030/31"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["academicYear"] == "2030/31" and body["source"] == "upload"
    kinds = {ch["type"] for ch in body["changes"]}
    assert "field_removed" in kinds and "field_added" in kinds


@pytest.mark.asyncio
async def test_assisted_ingest_from_url_rejects_bad_scheme(ctx):
    c, h = ctx
    r = await c.post("/api/v1/report-advisories/ingest-from-url", headers=h,
                     json={"packCode": BASE_CODE, "academicYear": "2031/32", "url": "ftp://nope"})
    assert r.status_code == 400
