"""Nested XML of a statutory return, shaped like HESA Data Futures (Demo 2 item 1.10).

The flat XML (``xml_return``) is one record per row. Data Futures nests a student's year:

    <Return structure="nested" schemaValidated="false">
      <Student>                      one per person (HUSID)
        <Engagement>                 one per registration (the student record)
          <Leaver/>                  when the engagement ended
          <StudentCourseSession>     one per programme period in the year
            <SessionStatus/>         each dated status in the period
            <ModuleInstance/>        each module taken in the period
            <SupervisorAllocation/>  each supervisor in the period

Where a field goes is decided by where its value comes from in the profile's mapping, so it
follows the institution's own configuration: ``person.*`` → Student, ``engagement.*`` →
Engagement, ``leaver.*`` → Leaver, everything else (``student.*``, ``programme.*``, ``funding.*`` …)
→ StudentCourseSession; HUSID and the student identifier sit on Student. Mapped fields keep exactly
the CSV's value (transforms, defaults and any amendment included).

The child entities (status, module, supervisor) come straight from the dated history, with the
element names in ``CHILDREN`` below. **Not yet validated against HESA's XSD**: when the collection's
XSD is available, align ``CHILDREN`` and ``ENTITY_OF_SOURCE`` with it and validate the output; the
root says ``schemaValidated="false"`` until then.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from xml.etree import ElementTree as ET

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.exports.xml_return import XML_MEDIA_TYPE, element_name  # noqa: F401 (re-exported)

_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")

# Which entity a mapped field belongs to, by the start of its source expression.
ENTITY_OF_SOURCE = (
    ("person.", "Student"),
    ("engagement.", "Engagement"),
    ("leaver.", "Leaver"),
)
# Fields whose source is on the student record but that identify the person (HESA Student).
STUDENT_SOURCES = {"student.husid"}
# Fallback by field code, for fields with no telling source (e.g. filled from a default): HESA's
# person-level (Student) fields, and the Engagement / Leaver ones.
ENTITY_OF_CODE = {
    **{c: "Student" for c in ("HUSID", "SID", "SURNAME", "FNAMES", "BIRTHDTE", "NATION", "NATIONALITY",
                              "ETHNIC", "DISABLE", "SEXID", "SEXORT", "GENDERID", "RELBLF")},
    **{c: "Engagement" for c in ("NUMHUS", "ENGSTARTDATE", "ENGEXPECTEDENDDATE", "FEEELIG", "ENGPRINONUK",
                                 "RCSTDNT", "UKRISRN")},
    **{c: "Leaver" for c in ("ENGENDDATE", "RSNENGEND")},
}
KEY_FIELDS = ("OWNSTU", "NUMHUS")

# Engagement and Leaver values from the dated history, written when the profile doesn't map the
# field itself (a mapped field always wins, with its CSV value).
ENGAGEMENT_FIELDS = (("NUMHUS", "numhus"), ("ENGSTARTDATE", "startDate"), ("ENGEXPECTEDENDDATE", "expectedEndDate"),
                     ("FEEELIG", "feeEligibility"), ("ENGPRINONUK", "primarilyOutsideUk"),
                     ("RCSTDNT", "researchCouncilStudent"), ("UKRISRN", "studentshipRef"),
                     ("STUDYINTENTION", "studyIntention"), ("INCOMINGEXCHANGE", "incomingExchange"))
LEAVER_FIELDS = (("ENGENDDATE", "endDate"), ("ENDSTATUS", "status"), ("RSNENGEND", "reason"))

# Child entities built from the record's child lists: element, list key, [(field code, item key)].
CHILDREN = (
    ("SessionStatus", "statusHistory", (("STATUSVALIDFROM", "validFrom"), ("STATUSVALIDTO", "validTo"),
                                        ("STATUSCHANGEDTO", "status"))),
    ("ModuleInstance", "modules", (("MODID", "code"), ("MODTITLE", "title"), ("MODVERSION", "version"),
                                   ("CRDTPTS", "credits"), ("MODFTE", "ftePct"),
                                   ("MODINSTSTARTDATE", "startDate"), ("MODINSTENDDATE", "endDate"),
                                   ("MODSTAT", "status"), ("MODOUT", "outcome"), ("MODMARK", "mark"))),
    ("SupervisorAllocation", "supervisors", (("SUPROLE", "role"), ("SUPPROPORTION", "weightingPct"),
                                             ("SUPUOA", "uoa"), ("SUPSTARTDATE", "validFrom"),
                                             ("SUPENDDATE", "validTo"))),
)


def entity_of(source: str | None, code: str = "") -> str:
    src = (source or "").strip()
    if src in STUDENT_SOURCES:
        return "Student"
    for prefix, entity in ENTITY_OF_SOURCE:
        if src.startswith(prefix):
            return entity
    return ENTITY_OF_CODE.get(code.upper(), "StudentCourseSession")


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (date, datetime)):
        return v.date().isoformat() if isinstance(v, datetime) else v.isoformat()
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if hasattr(v, "value"):        # enums
        v = v.value
    return _ILLEGAL.sub("", str(v))


def _put(parent, name: str, value: str) -> None:
    if value != "":
        ET.SubElement(parent, element_name(name)).text = value


def _key(header: list[str]) -> int:
    for f in KEY_FIELDS:
        if f in header:
            return header.index(f)
    return 0


def build(header: list[str], rows: list[list], records: list[dict], sources: dict[str, str | None],
          **meta) -> bytes:
    """``rows`` and ``records`` are matched by the record key (OWNSTU); ``sources`` maps each field
    code to its mapping's source expression. ``meta``: code, academicYear, asAt, knownAt, version …"""
    groups = {f: entity_of(sources.get(f), f) for f in header}
    in_header = set(header)
    k = _key(header)
    row_of = {str(r[k]): r for r in rows if k < len(r)}

    root = ET.Element("Return", {key: str(v) for key, v in {
        **meta, "structure": "nested", "schemaValidated": "false",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }.items() if v is not None})

    students: dict[str, ET.Element] = {}
    engagements: dict[str, ET.Element] = {}
    sessions = 0
    for rec in records:
        st = rec.get("student") or {}
        ref = str(st.get("ref") or "")
        row = row_of.get(ref)
        if row is None:        # not in the return (filtered out, or a later version dropped it)
            continue
        values = {f: ("" if i >= len(row) or row[i] is None else str(row[i])) for i, f in enumerate(header)}
        person_key = str(st.get("husid") or ref.split("::")[0])
        engagement_key = ref.split("::")[0]

        student_el = students.get(person_key)
        if student_el is None:
            student_el = ET.SubElement(root, "Student")
            students[person_key] = student_el
            for f in header:
                if groups[f] == "Student":
                    _put(student_el, f, values[f])

        eng_el = engagements.get(engagement_key)
        if eng_el is None:
            eng_el = ET.SubElement(student_el, "Engagement")
            engagements[engagement_key] = eng_el
            for f in header:
                if groups[f] == "Engagement":
                    _put(eng_el, f, values[f])
            eng = rec.get("engagement") or {}
            for code, item_key in ENGAGEMENT_FIELDS:
                if code not in in_header:
                    _put(eng_el, code, _text(eng.get(item_key)))
            lv_rec = rec.get("leaver") or {}
            leaver = [(f, values[f]) for f in header if groups[f] == "Leaver" and values[f] != ""]
            leaver += [(code, _text(lv_rec.get(item_key))) for code, item_key in LEAVER_FIELDS
                       if code not in in_header and _text(lv_rec.get(item_key)) != ""]
            if leaver:
                lv = ET.SubElement(eng_el, "Leaver")
                for f, value in leaver:
                    _put(lv, f, value)

        scs = ET.SubElement(eng_el, "StudentCourseSession")
        sessions += 1
        for f in header:
            if groups[f] == "StudentCourseSession":
                _put(scs, f, values[f])
        for element, list_key, fields in CHILDREN:
            for item in rec.get(list_key) or []:
                child = ET.SubElement(scs, element)
                for code, item_key in fields:
                    _put(child, code, _text(item.get(item_key)))

    root.set("students", str(len(students)))
    root.set("engagements", str(len(engagements)))
    root.set("courseSessions", str(sessions))
    root.insert(0, ET.Comment(" Nested in the shape of HESA Data Futures; not yet validated against the HESA XSD. "))
    ET.indent(root)
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def _name(code: str, year: str, suffix: str) -> str:
    return f"{code.lower()}_{year.replace('/', '-')}_{suffix}_nested.xml"


async def live(session: AsyncSession, profile_id: uuid.UUID, *, as_at: date | None = None,
               known_at: datetime | None = None) -> tuple[bytes, str]:
    from app.modules.exports.statutory import StatutoryEngine

    engine = StatutoryEngine(session)
    result = await engine.generate(profile_id, as_at=as_at, known_at=known_at, issue_limit=0, include_records=True)
    profile = await engine.get_profile(profile_id)
    sources = {m.target_field: m.source_expression for m in await engine._mappings(profile_id)}
    v = result["validation"]
    data = build(result["header"], result["rows"], result["records"], sources,
                 code=profile.code, academicYear=profile.academic_year, asAt=result["asAt"],
                 knownAt=result["knownAt"], errors=v["errors"], warnings=v["warnings"])
    stamp = as_at.isoformat() if as_at else datetime.now(timezone.utc).strftime("%Y%m%d")
    return data, _name(profile.code, profile.academic_year, stamp)


async def frozen(session: AsyncSession, profile, version) -> tuple[bytes, str]:
    """A signed-off version, nested: its own rows (exactly as frozen), with the child entities
    rebuilt from the data as it was known at that moment (the snapshot guarantees the same data)."""
    from app.modules.exports.statutory import StatutoryEngine

    engine = StatutoryEngine(session)
    from app.modules.exports.statutory import mapped_custom_keys

    mappings = await engine._mappings(profile.id)
    records = await engine.build_records(academic_year=version.academic_year, as_at=version.as_at,
                                         known_at=version.known_at, custom_keys=mapped_custom_keys(mappings))
    sources = {m.target_field: m.source_expression for m in mappings}
    data = build(version.header, version.rows, records, sources,
                 code=profile.code, academicYear=version.academic_year, version=f"v{version.version_no}",
                 asAt=version.as_at.isoformat() if version.as_at else None,
                 knownAt=version.known_at.isoformat() if version.known_at else None,
                 errors=version.errors, warnings=version.warnings)
    return data, _name(profile.code, version.academic_year,
                       f"v{version.version_no}_{version.known_at.strftime('%Y%m%d')}")
