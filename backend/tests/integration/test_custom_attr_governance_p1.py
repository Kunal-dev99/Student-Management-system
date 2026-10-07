"""Custom attribute governance, Phase 1 — request → maker-checker decision → active.

What must hold (plan Phase 1 acceptance criteria):
- there is no one-step create: an attribute starts as a pending request
- a pending (or rejected) attribute is not mappable, takes no values and isn't read by a return
- the requester can't decide their own request
- rejection needs a reason; approval and rejection are recorded (decision trail + audit log)
- once approved and activated, the existing HESA flow works exactly as before
"""
from __future__ import annotations

from datetime import date

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
from app.modules.audit.models import AuditLog
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student

REQ = "/api/v1/students/custom-attribute-requests"
BODY = {"label": "Care leaver", "dataType": "code", "reason": "HESA CARELEAVER is not in the core model."}


@pytest_asyncio.fixture
async def gov():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = {c: Permission(code=c) for c in PERMISSIONS}
        s.add_all(perms.values()); await s.flush()

        async def role(name, codes):
            r = Role(name=name); s.add(r); await s.flush()
            await s.refresh(r, ["permissions"]); r.permissions = [perms[c] for c in codes]
            return r

        admin = await role("Institution Administrator", [c for c in PERMISSIONS if c != "platform.configure"])
        # Runs the return: may request, may not decide.
        maker = await role("PGR Administrator", ["student.read", "student.write", "reporting.read",
                                                 "custom_attribute.request"])
        reader = await role("Supervisor", ["student.read"])
        for email, r in (("admin1@t.com", admin), ("admin2@t.com", admin),
                         ("maker@t.com", maker), ("reader@t.com", reader)):
            u = User(email=email, password_hash=hash_password("pw"), is_active=True)
            s.add(u); await s.flush(); await s.refresh(u, ["roles"]); u.roles = [r]

        prog = Programme(name="PhD CS", code="PHD-CS"); s.add(prog); await s.flush()
        person = Person(given_name="Ada", family_name="Lovelace", nationality="British")
        s.add(person); await s.flush()
        s.add(Student(person_id=person.id, student_ref="PGR-A", programme_id=prog.id,
                      start_date=date(2026, 10, 1), expected_end_date=date(2029, 9, 30),
                      study_mode=StudyMode.full_time, status=StudentStatus.active))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        hs = {}
        for who in ("admin1", "admin2", "maker", "reader"):
            tok = (await c.post("/api/v1/auth/login", json={"email": f"{who}@t.com", "password": "pw"})).json()
            hs[who] = {"Authorization": f"Bearer {tok['accessToken']}"}
        yield c, hs, sm
    app.dependency_overrides.clear()
    await eng.dispose()


async def _profile(c, h):
    return (await c.post("/api/v1/report-profiles", headers=h, json={
        "code": "HESA_STUDENT", "name": "HESA Student Return", "academicYear": "2026/27"})).json()


async def test_a_pending_request_is_inert(gov):
    c, hs, _ = gov
    r = await c.post(REQ, headers=hs["maker"], json=BODY)
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["status"] == "pending" and f["requestedByEmail"] == "maker@t.com"

    # Not offered for mapping, not in the live list, can't be mapped, takes no values.
    schema = (await c.get("/api/v1/report-profiles/record-schema", headers=hs["admin1"])).json()
    assert "custom.care_leaver" not in schema["paths"]
    assert (await c.get("/api/v1/students/custom-fields", headers=hs["admin1"])).json() == []
    p = await _profile(c, hs["admin1"])
    m = await c.post(f"/api/v1/report-profiles/{p['id']}/fields", headers=hs["admin1"],
                     json={"targetField": "CARELEAVER", "sourceExpression": "custom.care_leaver"})
    assert m.status_code == 400 and "pending" in m.json()["error"]["message"]
    v = await c.put(f"/api/v1/students/custom-fields/{f['id']}/values", headers=hs["admin1"],
                    json={"values": []})
    assert v.status_code == 422


async def test_full_flow_maker_checker_into_the_return(gov):
    c, hs, _ = gov
    f = (await c.post(REQ, headers=hs["admin1"], json=BODY)).json()

    # The requester can't decide their own request — even holding the approve permission.
    own = await c.post(f"{REQ}/{f['id']}/approve", headers=hs["admin1"], json={})
    assert own.status_code == 403 and "maker-checker" in own.json()["error"]["message"]

    ok = await c.post(f"{REQ}/{f['id']}/approve", headers=hs["admin2"], json={"reason": "Needed for 26/27"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "approved" and ok.json()["decidedByEmail"] == "admin2@t.com"
    # Approved isn't live yet.
    schema = (await c.get("/api/v1/report-profiles/record-schema", headers=hs["admin1"])).json()
    assert "custom.care_leaver" not in schema["paths"]

    act = await c.post(f"{REQ}/{f['id']}/activate", headers=hs["admin2"])
    assert act.status_code == 200 and act.json()["status"] == "active"
    assert (await c.post(f"{REQ}/{f['id']}/activate", headers=hs["admin2"])).status_code == 409

    # Now it behaves exactly like the old attribute: mappable, enterable, in the export.
    schema = (await c.get("/api/v1/report-profiles/record-schema", headers=hs["admin1"])).json()
    assert "custom.care_leaver" in schema["paths"]
    grid = (await c.get(f"/api/v1/students/custom-fields/{f['id']}/values", headers=hs["admin1"])).json()
    sid = grid["rows"][0]["studentId"]
    put = await c.put(f"/api/v1/students/custom-fields/{f['id']}/values", headers=hs["admin1"],
                      json={"values": [{"studentId": sid, "value": "01"}]})
    assert put.status_code == 200 and put.json()["filled"] == 1
    p = await _profile(c, hs["admin1"])
    for target, src in (("HUSID", "student.ref"), ("CARELEAVER", "custom.care_leaver")):
        r = await c.post(f"/api/v1/report-profiles/{p['id']}/fields", headers=hs["admin1"],
                         json={"targetField": target, "sourceExpression": src})
        assert r.status_code == 201, r.text
    job = (await c.post(f"/api/v1/report-profiles/{p['id']}/generate", headers=hs["admin1"], json={})).json()["job"]
    csv_text = (await c.get(f"/api/v1/exports/{job['id']}/download", headers=hs["admin1"])).text
    assert csv_text.strip().splitlines() == ["HUSID,CARELEAVER", "PGR-A,01"]

    # The decision trail reads requested → assessed (automatic) → approved → activated.
    detail = (await c.get(f"{REQ}/{f['id']}", headers=hs["admin1"])).json()
    assert [e["action"] for e in reversed(detail["events"])] == ["requested", "assessed", "approved", "activated"]
    assert next(e for e in detail["events"] if e["action"] == "approved")["notes"] == "Needed for 26/27"


async def test_approve_and_activate_in_one_step(gov):
    c, hs, _ = gov
    f = (await c.post(REQ, headers=hs["maker"], json=BODY)).json()
    r = await c.post(f"{REQ}/{f['id']}/approve", headers=hs["admin1"], json={"activate": True})
    assert r.status_code == 200 and r.json()["status"] == "active"
    detail = (await c.get(f"{REQ}/{f['id']}", headers=hs["admin1"])).json()
    assert [e["action"] for e in reversed(detail["events"])] == ["requested", "assessed", "approved", "activated"]


async def test_rejection_needs_a_reason_and_is_final(gov):
    c, hs, sm = gov
    f = (await c.post(REQ, headers=hs["maker"], json=BODY)).json()
    assert (await c.post(f"{REQ}/{f['id']}/reject", headers=hs["admin1"], json={})).status_code == 400
    assert (await c.post(f"{REQ}/{f['id']}/reject", headers=hs["admin1"],
                         json={"reason": "   "})).status_code == 400
    r = await c.post(f"{REQ}/{f['id']}/reject", headers=hs["admin1"],
                     json={"reason": "Already held as person.care_leaver"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert r.json()["decisionReason"] == "Already held as person.care_leaver"
    # Decided → can't be approved, activated or withdrawn afterwards.
    assert (await c.post(f"{REQ}/{f['id']}/approve", headers=hs["admin2"], json={})).status_code == 409
    assert (await c.post(f"{REQ}/{f['id']}/activate", headers=hs["admin2"])).status_code == 409
    assert (await c.delete(f"{REQ}/{f['id']}", headers=hs["admin2"])).status_code == 409
    # The same key can't be requested again silently.
    dup = await c.post(REQ, headers=hs["maker"], json=BODY)
    assert dup.status_code == 409 and "rejected" in dup.json()["error"]["message"]
    # Recorded in the general audit log too.
    async with sm() as s:
        actions = set((await s.execute(select(AuditLog.action))).scalars().all())
    assert {"custom_attribute.requested", "custom_attribute.rejected"} <= actions


async def test_permissions(gov):
    c, hs, _ = gov
    # A reader can't request, can't see requests, and only sees live attributes.
    assert (await c.post(REQ, headers=hs["reader"], json=BODY)).status_code == 403
    assert (await c.get(REQ, headers=hs["reader"])).status_code == 403
    assert (await c.get("/api/v1/students/custom-attributes?status=pending",
                        headers=hs["reader"])).status_code == 403
    assert (await c.get("/api/v1/students/custom-attributes", headers=hs["reader"])).status_code == 200
    # The maker can request and see the queue, but not decide.
    f = (await c.post(REQ, headers=hs["maker"], json=BODY)).json()
    queue = (await c.get(REQ, headers=hs["maker"])).json()
    assert [q["key"] for q in queue] == ["care_leaver"]
    for verb in ("approve", "reject", "activate"):
        r = await c.post(f"{REQ}/{f['id']}/{verb}", headers=hs["maker"], json={"reason": "x"})
        assert r.status_code == 403, verb
    # The old one-step create is gone.
    old = await c.post("/api/v1/students/custom-fields", headers=hs["admin1"], json=BODY)
    assert old.status_code == 405
    # A bad status filter is a 400, not a silent empty list.
    assert (await c.get(f"{REQ}?status=bogus", headers=hs["admin1"])).status_code == 400


async def test_withdraw(gov):
    c, hs, _ = gov
    f = (await c.post(REQ, headers=hs["maker"], json=BODY)).json()
    other = (await c.post(REQ, headers=hs["admin1"], json={**BODY, "label": "Refugee status"})).json()
    # The maker can't withdraw someone else's request (and holds no approve permission).
    assert (await c.delete(f"{REQ}/{other['id']}", headers=hs["maker"])).status_code == 403
    assert (await c.delete(f"{REQ}/{f['id']}", headers=hs["maker"])).status_code == 204
    assert (await c.get(f"{REQ}/{f['id']}", headers=hs["admin1"])).status_code == 404
    # The trail keeps the withdrawal even though the request row is gone.
    events = (await c.get("/api/v1/students/custom-attribute-events", headers=hs["admin1"])).json()
    assert any(e["action"] == "withdrawn" and e["key"] == "care_leaver" for e in events)
    # An active attribute can't be withdrawn.
    await c.post(f"{REQ}/{other['id']}/approve", headers=hs["admin2"], json={"activate": True})
    assert (await c.delete(f"{REQ}/{other['id']}", headers=hs["admin2"])).status_code == 409
