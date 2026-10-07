"""Excel workbooks of a statutory return, for people to review (Demo 2 item 1.10).

The submission file is still the CSV (and XML when that lands); the workbook is the same data laid
out for review, with nothing recalculated:

  Summary     the return, year, snapshot dates, record and issue counts, sign-off state
  Return      exactly the CSV: one row per record, the file's own column order and text
  Validation  every issue (not just the first 500 the screen shows): record, field, severity, message
  Fields      how each column is produced: source, transform, default, required, allowed values

A signed-off version is frozen, so its workbook has Summary and Return (the issues weren't kept).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.xlsx import Sheet, workbook


def _name(code: str, year: str, suffix: str) -> str:
    return f"{code.lower()}_{year.replace('/', '-')}_{suffix}.xlsx"


async def live(session: AsyncSession, profile_id: uuid.UUID, *, as_at: date | None = None,
               known_at: datetime | None = None) -> tuple[bytes, str]:
    from app.modules.exports.spec_release import list_versions
    from app.modules.exports.statutory import StatutoryEngine

    engine = StatutoryEngine(session)
    result = await engine.generate(profile_id, as_at=as_at, known_at=known_at, issue_limit=None)
    profile = await engine.get_profile(profile_id)
    # Governance Phase 6 — a downloaded return counts as a use of the attributes it read.
    await engine.note_usage(profile, purpose="download", row_count=result["rowCount"])
    await session.commit()
    mappings = await engine._mappings(profile_id)
    v = result["validation"]
    # The version for exactly this year (the resolver may fall back to another year's for fields,
    # but the review sheet must name the version this return's year actually has).
    spec = next((x for x in await list_versions(session, profile.code, profile.academic_year)
                 if getattr(x.status, "value", x.status) == "active"), None)
    now = datetime.now(timezone.utc)

    summary = Sheet("Summary", ["Item", "Value"], [
        ["Return", profile.name],
        ["Specification", f"{profile.code} {profile.academic_year}"],
        ["Specification version", f"v{spec.version}" if spec else "baseline"],
        ["Values as at", result["asAt"] or "end of the reporting year"],
        ["Data as recorded at", result["knownAt"] or "now"],
        ["Generated (UTC)", now.strftime("%Y-%m-%d %H:%M")],
        ["Records", result["rowCount"]],
        ["Errors", v["errors"]],
        ["Warnings", v["warnings"]],
        ["Valid for submission", "Yes" if v["valid"] else "No - fix the errors first"],
        ["Signed off", profile.signed_off_at.strftime("%Y-%m-%d %H:%M") if profile.signed_off_at else "No"],
        ["Note", "For review. Submit the CSV (or XML) file, not this workbook."],
    ])
    data = Sheet("Return", result["header"], result["rows"])
    issues = Sheet("Validation", ["Record", "Field", "Severity", "Message", "Rule", "Allowed values"], [
        [i.get("studentRef"), i.get("field"), i.get("severity"), i.get("message"), i.get("ruleKey"),
         ", ".join(i.get("allowed") or [])]
        for i in v["issues"]
    ])
    fields = Sheet("Fields", ["Position", "Field", "Source", "Transform", "Default", "Required", "Allowed values"], [
        [m.position, m.target_field, m.source_expression or "", m.transform or "", m.default_value or "",
         "Yes" if m.required else "No", ", ".join(m.allowed_values or [])]
        for m in mappings
    ])
    stamp = (as_at.isoformat() if as_at else now.strftime("%Y%m%d"))
    return workbook([summary, data, issues, fields]), _name(profile.code, profile.academic_year, f"review_{stamp}")


def frozen(profile, version) -> tuple[bytes, str]:
    summary = Sheet("Summary", ["Item", "Value"], [
        ["Return", profile.name],
        ["Specification", f"{profile.code} {version.academic_year}"],
        ["Return version", f"v{version.version_no} ({version.reason.replace('_', ' ')})"],
        ["Values as at", version.as_at.isoformat() if version.as_at else "end of the reporting year"],
        ["Data as recorded at", version.known_at.strftime("%Y-%m-%d %H:%M")],
        ["Records", version.row_count],
        ["Errors at sign-off", version.errors],
        ["Warnings at sign-off", version.warnings],
        ["Note", "Frozen at sign-off: exactly what was submitted. For review only."],
    ])
    data = Sheet("Return", version.header, version.rows)
    name = _name(profile.code, version.academic_year,
                 f"v{version.version_no}_{version.known_at.strftime('%Y%m%d')}")
    return workbook([summary, data]), name
