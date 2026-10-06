"""XML output of a statutory return (Demo 2 item 1.10).

The same data as the CSV, as XML: one ``<Record>`` per return row, one element per field, named by
its field code (``<OWNSTU>``, ``<STULOAD>``) and holding exactly the CSV's text, so codes keep their
leading zeros. Empty fields are left out, as HESA XML does. A header records the return, year,
snapshot dates and validation counts.

    <Return code="HESA_STUDENT" academicYear="2025/26" asAt="2026-07-31" knownAt="..." records="697">
      <Validation errors="0" warnings="7" valid="true"/>
      <Record><OWNSTU>ED-DEMO-01</OWNSTU><STULOAD>62</STULOAD>...</Record>
    </Return>

The nesting is one level (a record per row). HESA Data Futures nests entities (Student →
Engagement → StudentCourseSession → SessionStatus / ModuleInstance) and validates against the
collection's XSD; mapping fields to those entities is the next step and needs that XSD.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from xml.etree import ElementTree as ET

from sqlalchemy.ext.asyncio import AsyncSession

XML_MEDIA_TYPE = "application/xml"
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


def element_name(field: str) -> str:
    """A field code as an XML element name: kept as is when valid, else made valid."""
    if _NAME.match(field or "") and not field.lower().startswith("xml"):
        return field
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", field or "")
    return cleaned if cleaned and _NAME.match(cleaned) and not cleaned.lower().startswith("xml") else f"F_{cleaned}"


def _attrs(**kw) -> dict[str, str]:
    return {k: str(v) for k, v in kw.items() if v is not None}


def build(header: list[str], rows: list[list], **meta) -> bytes:
    """``meta``: code, academicYear, asAt, knownAt, version, errors, warnings, valid."""
    errors, warnings, valid = meta.pop("errors", None), meta.pop("warnings", None), meta.pop("valid", None)
    root = ET.Element("Return", _attrs(**meta, records=len(rows),
                                       generated=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
    if errors is not None:
        ET.SubElement(root, "Validation", _attrs(errors=errors, warnings=warnings,
                                                 valid=str(bool(valid)).lower()))
    names = [element_name(h) for h in header]
    for row in rows:
        rec = ET.SubElement(root, "Record")
        for name, value in zip(names, row):
            text = "" if value is None else _ILLEGAL.sub("", str(value))
            if text != "":
                ET.SubElement(rec, name).text = text
    ET.indent(root)
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def _name(code: str, year: str, suffix: str) -> str:
    return f"{code.lower()}_{year.replace('/', '-')}_{suffix}.xml"


async def live(session: AsyncSession, profile_id: uuid.UUID, *, as_at: date | None = None,
               known_at: datetime | None = None) -> tuple[bytes, str]:
    from app.modules.exports.statutory import StatutoryEngine

    engine = StatutoryEngine(session)
    result = await engine.generate(profile_id, as_at=as_at, known_at=known_at, issue_limit=0)
    profile = await engine.get_profile(profile_id)
    # Governance Phase 6 — a downloaded return counts as a use of the attributes it read.
    await engine.note_usage(profile, purpose="download", row_count=result["rowCount"])
    await session.commit()
    v = result["validation"]
    data = build(result["header"], result["rows"], code=profile.code, academicYear=profile.academic_year,
                 asAt=result["asAt"], knownAt=result["knownAt"],
                 errors=v["errors"], warnings=v["warnings"], valid=v["valid"])
    stamp = as_at.isoformat() if as_at else datetime.now(timezone.utc).strftime("%Y%m%d")
    return data, _name(profile.code, profile.academic_year, stamp)


def frozen(profile, version) -> tuple[bytes, str]:
    data = build(version.header, version.rows, code=profile.code, academicYear=version.academic_year,
                 version=f"v{version.version_no}",
                 asAt=version.as_at.isoformat() if version.as_at else None,
                 knownAt=version.known_at.isoformat() if version.known_at else None,
                 errors=version.errors, warnings=version.warnings, valid=version.errors == 0)
    return data, _name(profile.code, version.academic_year,
                       f"v{version.version_no}_{version.known_at.strftime('%Y%m%d')}")
