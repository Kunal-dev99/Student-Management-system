"""Nested XML in the shape of HESA Data Futures (Demo 2 item 1.10).

Student → Engagement (+ Leaver) → StudentCourseSession → SessionStatus / ModuleInstance. A field's
entity follows its mapping source (person.* → Student …), mapped values are the CSV's own, and a
frozen version keeps its frozen values with the children rebuilt as known at sign-off.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from xml.etree import ElementTree as ET

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.exports.models import ReportReturnVersion
from app.modules.exports.xml_nested import build, entity_of
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.constants import ProgrammeType, StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student
from app.modules.taught.models import ModuleEnrolment, TaughtModule


def test_entity_follows_the_mapping_source_then_the_field_code():
    assert entity_of("person.familyName", "SURNAME") == "Student"
    assert entity_of("student.husid", "HUSID") == "Student"
    assert entity_of("engagement.startDate", "X") == "Engagement"
    assert entity_of("leaver.reason", "X") == "Leaver"
    assert entity_of("student.fteLoad", "STULOAD") == "StudentCourseSession"
    assert entity_of(None, "ETHNIC") == "Student"            # a default-only field, placed by its code
    assert entity_of(None, "WHATEVER") == "StudentCourseSession"


def test_a_transfer_is_one_engagement_with_two_course_sessions():
    header = ["OWNSTU", "HUSID", "SURNAME", "COURSEID"]
    sources = {"OWNSTU": "student.ref", "HUSID": "student.husid", "SURNAME": "person.familyName",
               "COURSEID": "programme.code"}
    rows = [["S1::A::2025-08-01", "H1", "SMITH", "A"], ["S1::B::2026-02-02", "H1", "SMITH", "B"]]
    recs = [{"student": {"ref": r[0], "husid": "H1"}, "engagement": {"numhus": "S1", "startDate": date(2024, 10, 1)},
             "leaver": {}, "statusHistory": [{"status": "active", "validFrom": date(2025, 8, 1), "validTo": None}],
             "modules": [], "supervisors": []} for r in rows]
    root = ET.fromstring(build(header, rows, recs, sources, code="HESA_STUDENT", academicYear="2025/26"))
    assert root.get("structure") == "nested" and root.get("schemaValidated") == "false"
    (student,) = root.findall("Student")
    assert student.findtext("HUSID") == "H1" and student.findtext("SURNAME") == "SMITH"
    (eng,) = student.findall("Engagement")
    assert eng.findtext("NUMHUS") == "S1" and eng.findtext("ENGSTARTDATE") == "2024-10-01"
    assert [s.findtext("COURSEID") for s in eng.findall("StudentCourseSession")] == ["A", "B"]
    assert eng.find("StudentCourseSession/SessionStatus/STATUSCHANGEDTO").text == "active"
    assert (root.get("students"), root.get("engagements"), root.get("courseSessions")) == ("1", "1", "2")


@pytest_asyncio.fixture
async def ctx():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        perms = [Permission(code=c) for c in PERMISSIONS]
        s.add_all(perms); await s.flush()
        role = Role(name="Institution Administrator"); s.add(role); await s.flush()
        await s.refresh(role, ["permissions"]); role.permissions = perms
        user = User(email="a@inst.example.com", password_hash=hash_password("pw"), is_active=True)
        s.add(user); await s.flush(); await s.refresh(user, ["roles"]); user.roles = [role]
        prog = Programme(name="MSc Onc", code="MSC-ONC", programme_type=ProgrammeType.taught, taught_total_credits=180)
        s.add(prog); await s.flush()
        mod = TaughtModule(programme_id=prog.id, code="ONC501", title="Oncology 1", credits=60)
        s.add(mod); await s.flush()
        person = Person(given_name="Ada", family_name="Lovelace", nationality="British")
        s.add(person); await s.flush()
        st = Student(person_id=person.id, student_ref="0042", programme_id=prog.id, start_date=date(2026, 9, 1),
                     expected_end_date=date(2027, 9, 30), study_mode=StudyMode.full_time, status=StudentStatus.active)
        s.add(st); await s.flush()
        s.add(ModuleEnrolment(student_id=st.id, module_id=mod.id, academic_year="2026/27",
                              start_date=date(2026, 9, 1), end_date=date(2027, 6, 30)))
        await s.commit()

    async def _override():
        async with sm() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_read_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/auth/login", json={"email": "a@inst.example.com", "password": "pw"})
        h = {"Authorization": f"Bearer {r.json()['accessToken']}"}
        pid = (await c.post("/api/v1/report-profiles", headers=h, json={
            "code": "HESA_STUDENT", "name": "HESA Student Return", "academicYear": "2026/27"})).json()["id"]
        for target, source in (("OWNSTU", "student.ref"), ("SURNAME", "person.familyName"),
                               ("NATION", "person.nationality"), ("COURSEID", "programme.code")):
            await c.post(f"/api/v1/report-profiles/{pid}/fields", headers=h,
                         json={"targetField": target, "sourceExpression": source})
        yield c, h, pid, sm
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_live_nested_xml(ctx):
    c, h, pid, _ = ctx
    r = await c.get(f"/api/v1/report-profiles/{pid}/xml", headers=h, params={"nested": "true"})
    assert r.status_code == 200, r.text
    assert "_nested.xml" in r.headers["content-disposition"]
    root = ET.fromstring(r.content)
    student = root.find("Student")
    assert (student.findtext("SURNAME"), student.findtext("NATION")) == ("Lovelace", "British")
    scs = student.find("Engagement/StudentCourseSession")
    assert (scs.findtext("OWNSTU"), scs.findtext("COURSEID")) == ("0042", "MSC-ONC")
    mi = scs.find("ModuleInstance")
    assert (mi.findtext("MODID"), mi.findtext("CRDTPTS"), mi.findtext("MODINSTSTARTDATE")) == ("ONC501", "60", "2026-09-01")
    assert student.find("Engagement").findtext("ENGSTARTDATE") == "2026-09-01"
    flat = ET.fromstring((await c.get(f"/api/v1/report-profiles/{pid}/xml", headers=h)).content)
    assert flat.find("Record") is not None and flat.get("structure") is None        # flat is unchanged


@pytest.mark.asyncio
async def test_frozen_nested_keeps_the_frozen_values(ctx):
    c, h, pid, sm = ctx
    async with sm() as s:
        v = ReportReturnVersion(profile_id=uuid.UUID(pid), version_no=1, academic_year="2026/27", as_at=None,
                                known_at=datetime(2027, 8, 1, tzinfo=timezone.utc), reason="sign_off",
                                created_at=datetime.now(timezone.utc), header=["OWNSTU", "SURNAME", "NATION", "COURSEID"],
                                rows=[["0042", "Lovelace", "Irish", "MSC-ONC"]], row_count=1, errors=0, warnings=0)
        s.add(v)
        await s.commit()
        vid = v.id
    r = await c.get(f"/api/v1/report-profiles/{pid}/versions/{vid}/download", headers=h, params={"format": "xml-nested"})
    assert r.status_code == 200, r.text
    root = ET.fromstring(r.content)
    assert root.get("version") == "v1"
    assert root.find("Student").findtext("NATION") == "Irish"            # the frozen value, not today's
    assert root.find("Student/Engagement/StudentCourseSession/ModuleInstance/MODID").text == "ONC501"
