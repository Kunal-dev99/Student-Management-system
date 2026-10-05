"""Demo 2 item 1.10 — an Excel workbook of the statutory return, for review.

The workbook is read back with the standard library (it's a zip of XML), so the test checks the
file a spreadsheet would open: four sheets, the Return sheet identical to the CSV, every issue
listed, codes kept as text (leading zeros intact), and a frozen version downloadable as Excel.
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import date
from xml.etree import ElementTree as ET

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.core.xlsx import Sheet, workbook
from app.db.base import Base
from app.db.session import get_read_session, get_session
from app.main import app
from app.modules.identity.constants import PERMISSIONS
from app.modules.identity.models import Permission, Role, User
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def read_xlsx(data: bytes) -> dict[str, list[list[str]]]:
    """Sheet name -> rows of cell text (inline strings and numbers)."""
    z = zipfile.ZipFile(io.BytesIO(data))
    assert z.testzip() is None
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = {r.get("Id"): r.get("Target") for r in rels}
    out = {}
    for sh in wb.find("m:sheets", NS):
        xml = ET.fromstring(z.read("xl/" + target[sh.get(REL)]))
        rows = []
        for row in xml.find("m:sheetData", NS):
            cells = []
            for c in row:
                t = c.find("m:is/m:t", NS)
                v = c.find("m:v", NS)
                cells.append(t.text if t is not None else (v.text if v is not None else ""))
            rows.append(cells)
        out[sh.get("name")] = rows
    return out


def test_writer_keeps_codes_as_text_and_cleans_names():
    data = workbook([Sheet("Codes: 2026/27?", ["CODE", "N"], [["01", 7], ["A&B <x>", None], ["bad\x01char", 2.5]])])
    sheets = read_xlsx(data)
    (name, rows), = sheets.items()
    assert name == "Codes- 2026-27-"
    assert rows[0] == ["CODE", "N"] and rows[1] == ["01", "7"] and rows[2] == ["A&B <x>"]
    assert rows[3] == ["badchar", "2.5"]


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
        prog = Programme(name="PhD CS", code="PHD-CS"); s.add(prog); await s.flush()
        full = Person(given_name="Ada", family_name="Complete", nationality="British")
        partial = Person(given_name="Bo", family_name="Missing")
        s.add_all([full, partial]); await s.flush()
        for person, ref in ((full, "0042"), (partial, "PGR-B")):
            s.add(Student(person_id=person.id, student_ref=ref, programme_id=prog.id,
                          start_date=date(2026, 10, 1), expected_end_date=date(2029, 9, 30),
                          study_mode=StudyMode.full_time, status=StudentStatus.active))
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
        for target, source, extra in (("OWNSTU", "student.ref", {}),
                                      ("NATION", "person.nationality", {"required": True})):
            await c.post(f"/api/v1/report-profiles/{pid}/fields", headers=h,
                         json={"targetField": target, "sourceExpression": source, **extra})
        yield c, h, pid, sm
    app.dependency_overrides.clear()
    await eng.dispose()


@pytest.mark.asyncio
async def test_workbook_matches_the_csv_and_lists_every_issue(ctx):
    c, h, pid, _ = ctx
    gen = (await c.post(f"/api/v1/report-profiles/{pid}/generate", headers=h)).json()
    csv_text = (await c.get(f"/api/v1/exports/{gen['job']['id']}/download", headers=h)).text
    csv_rows = list(csv.reader(io.StringIO(csv_text)))

    r = await c.get(f"/api/v1/report-profiles/{pid}/workbook", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml")
    assert r.headers["content-disposition"].endswith('.xlsx"') or ".xlsx" in r.headers["content-disposition"]
    sheets = read_xlsx(r.content)
    assert list(sheets) == ["Summary", "Return", "Validation", "Fields"]

    ret = [row + [""] * (len(sheets["Return"][0]) - len(row)) for row in sheets["Return"]]
    assert ret == csv_rows                                   # same data, same order
    assert ["0042", "British"] in ret                        # leading zero kept as text
    issues = sheets["Validation"][1:]
    assert len(issues) == gen["validation"]["issueCount"] == 1
    assert issues[0][:3] == ["PGR-B", "NATION", "error"]
    summary = dict((row + [""])[:2] for row in sheets["Summary"][1:])
    assert summary["Records"] == "2" and summary["Errors"] == "1" and summary["Valid for submission"].startswith("No")
    assert [row[1] for row in sheets["Fields"][1:]] == ["OWNSTU", "NATION"]


@pytest.mark.asyncio
async def test_frozen_version_downloads_as_excel(ctx):
    import uuid
    from datetime import datetime, timezone

    from app.modules.exports.models import ReportReturnVersion

    c, h, pid, sm = ctx
    async with sm() as s:   # a version frozen at sign-off (signing off needs every HESA field mapped)
        v = ReportReturnVersion(profile_id=uuid.UUID(pid), version_no=1, academic_year="2026/27", as_at=None,
                                known_at=datetime(2027, 8, 1, tzinfo=timezone.utc), reason="sign_off",
                                created_at=datetime.now(timezone.utc), header=["OWNSTU", "NATION"],
                                rows=[["0042", "British"], ["PGR-B", "Unknown"]], row_count=2, errors=0, warnings=0)
        s.add(v)
        await s.commit()
        vid = v.id
    r = await c.get(f"/api/v1/report-profiles/{pid}/versions/{vid}/download", headers=h, params={"format": "xlsx"})
    assert r.status_code == 200, r.text
    sheets = read_xlsx(r.content)
    assert list(sheets) == ["Summary", "Return"]
    assert sheets["Return"] == [["OWNSTU", "NATION"], ["0042", "British"], ["PGR-B", "Unknown"]]
    assert "v1_20270801" in r.headers["content-disposition"]
    csv_r = await c.get(f"/api/v1/report-profiles/{pid}/versions/{vid}/download", headers=h)
    assert csv_r.headers["content-type"].startswith("text/csv")            # CSV stays the default
    assert (await c.get(f"/api/v1/report-profiles/{pid}/versions/{vid}/download", headers=h,
                        params={"format": "pdf"})).status_code == 422


@pytest.mark.asyncio
async def test_xml_matches_the_csv(ctx):
    """Demo 2 item 1.10 — XML: a Record per row, an element per field code, CSV text kept exactly."""
    c, h, pid, sm = ctx
    gen = (await c.post(f"/api/v1/report-profiles/{pid}/generate", headers=h)).json()
    csv_rows = list(csv.reader(io.StringIO(
        (await c.get(f"/api/v1/exports/{gen['job']['id']}/download", headers=h)).text)))
    r = await c.get(f"/api/v1/report-profiles/{pid}/xml", headers=h)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/xml") and ".xml" in r.headers["content-disposition"]
    root = ET.fromstring(r.content)
    assert root.tag == "Return" and root.get("academicYear") == "2026/27" and root.get("records") == "2"
    assert root.find("Validation").get("errors") == "1"
    records = [{el.tag: el.text for el in rec} for rec in root.findall("Record")]
    expected = [{k: v for k, v in zip(csv_rows[0], row) if v != ""} for row in csv_rows[1:]]
    assert records == expected
    assert {"OWNSTU": "0042", "NATION": "British"} in records          # leading zero kept
    assert {"OWNSTU": "PGR-B"} in records                               # empty field left out

    import uuid
    from datetime import datetime, timezone

    from app.modules.exports.models import ReportReturnVersion
    async with sm() as s:
        v = ReportReturnVersion(profile_id=uuid.UUID(pid), version_no=1, academic_year="2026/27", as_at=None,
                                known_at=datetime(2027, 8, 1, tzinfo=timezone.utc), reason="sign_off",
                                created_at=datetime.now(timezone.utc), header=["OWNSTU", "NATION"],
                                rows=[["0042", "British"]], row_count=1, errors=0, warnings=0)
        s.add(v)
        await s.commit()
        vid = v.id
    frozen = await c.get(f"/api/v1/report-profiles/{pid}/versions/{vid}/download", headers=h,
                         params={"format": "xml"})
    froot = ET.fromstring(frozen.content)
    assert froot.get("version") == "v1" and [[e.text for e in r] for r in froot.findall("Record")] == [["0042", "British"]]


def test_xml_element_names_are_always_valid():
    from app.modules.exports.xml_return import element_name

    assert element_name("OWNSTU") == "OWNSTU"
    assert element_name("1ST FIELD") == "F_1ST_FIELD"
    assert element_name("xmlThing").startswith("F_")


@pytest.mark.asyncio
async def test_snapshot_date_must_fall_inside_the_reporting_year(ctx):
    c, h, pid, _ = ctx
    outside = await c.get(f"/api/v1/report-profiles/{pid}/validate", headers=h, params={"asAt": "2027-10-05"})
    assert outside.status_code in (409, 422) and "outside the 2026/27 reporting year" in outside.text
    inside = await c.get(f"/api/v1/report-profiles/{pid}/validate", headers=h, params={"asAt": "2027-07-31"})
    assert inside.status_code == 200, inside.text
