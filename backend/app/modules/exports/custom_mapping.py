"""Custom attributes as governed mapping sources (custom attribute governance, Phase 4).

A mapping reads a custom attribute through ``custom.<key>``. This module answers, for one
report profile:

- which of its mappings depend on custom attributes, and which of those are **obsolete** — the
  attribute is retired, never went live, or no longer exists. An obsolete mapping would quietly
  produce blanks, so it blocks sign-off (and is reported when a profile is cloned forward);
- whether a proposed mapping is valid **before** it is saved (path, attribute state, transform,
  HESA compatibility), as errors that block and warnings that inform;
- the mapping picker for *this* profile: the core catalogue plus the live custom attributes,
  each with its type, status and HESA relevance to this return, and where it is already mapped.

Core-path mappings are untouched: an unrecognised core path is a warning, never an error, so
existing profiles keep working.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.exports.models import ReportFieldMapping, ReportProfile
from app.modules.exports.record_schema import RECORD_SCHEMA, as_dict
from app.modules.student_record.custom_fields import Status as CustomStatus
from app.modules.student_record.models import StudentCustomField

_CORE_PATHS = {f.path: f for g in RECORD_SCHEMA for f in g.fields}


def custom_key(expr: str | None) -> str | None:
    expr = (expr or "").strip()
    return expr[len("custom."):] if expr.startswith("custom.") else None


async def _fields_by_key(session: AsyncSession, keys) -> dict[str, StudentCustomField]:
    keys = {k for k in keys if k}
    if not keys:
        return {}
    rows = (await session.execute(select(StudentCustomField).where(StudentCustomField.key.in_(keys)))).scalars().all()
    return {f.key: f for f in rows}


def _obsolete_reason(key: str, field: StudentCustomField | None) -> str | None:
    if field is None:
        return f"There is no custom attribute '{key}'."
    if field.status not in CustomStatus.LIVE:
        return f"Custom attribute '{field.label}' is {field.status}."
    return None


async def profile_dependencies(session: AsyncSession, profile: ReportProfile, mappings=None) -> list[dict]:
    """One row per mapping: where it reads from, and whether that source is still usable."""
    if mappings is None:
        mappings = list((await session.execute(
            select(ReportFieldMapping).where(ReportFieldMapping.profile_id == profile.id)
            .order_by(ReportFieldMapping.position)
        )).scalars().all())
    fields = await _fields_by_key(session, (custom_key(m.source_expression) for m in mappings))
    out = []
    for m in mappings:
        src = (m.source_expression or "").strip()
        key = custom_key(src)
        row = {"mappingId": str(m.id), "targetField": m.target_field, "sourceExpression": src,
               "required": bool(m.required), "kind": "unmapped", "obsolete": False, "reason": None}
        if key is not None:
            f = fields.get(key)
            reason = _obsolete_reason(key, f)
            row.update(kind="custom", customKey=key, customId=str(f.id) if f else None,
                       customLabel=f.label if f else None, customStatus=f.status if f else None,
                       obsolete=reason is not None, reason=reason)
        elif src:
            row["kind"] = "core" if src in _CORE_PATHS else "unknown"
            if row["kind"] == "unknown":
                row["reason"] = f"'{src}' isn't in the record catalogue; it will read blank."
        out.append(row)
    return out


async def obsolete_mappings(session: AsyncSession, profile: ReportProfile, mappings=None) -> list[dict]:
    return [d for d in await profile_dependencies(session, profile, mappings) if d["obsolete"]]


async def _spec_field(session: AsyncSession, profile: ReportProfile, target: str) -> dict | None:
    from app.modules.exports.spec_resolver import resolve_fields

    for f in await resolve_fields(session, profile.code, profile.academic_year):
        if f.get("field") == target:
            return f
    return None


async def _spec_label(session: AsyncSession, profile: ReportProfile) -> str:
    """Which specification the profile is actually checked against — the same one the compile
    gate uses (an accepted version for the year, else the latest accepted, else the baseline)."""
    from app.modules.exports.spec_resolver import active_version_for_code

    row = await active_version_for_code(session, profile.code, profile.academic_year)
    if row is not None:
        return f"{row.pack_code} {row.academic_year} v{row.version}"
    return f"{profile.code} {profile.academic_year} baseline"


async def validate_mapping(
    session: AsyncSession, profile: ReportProfile, *, target_field: str, source_expression: str,
    transform: str | None = None, mapping_id=None,
) -> dict:
    """Check a mapping without saving it. ``errors`` would be refused on save; ``warnings`` are
    for the person mapping."""
    from app.modules.exports.statutory import _validate_transform_chain
    from app.core.errors import AppError

    errors: list[str] = []
    warnings: list[str] = []
    target = (target_field or "").strip()
    src = (source_expression or "").strip()
    if not target:
        errors.append("A target field is required.")
    else:
        clash = (await session.execute(
            select(ReportFieldMapping.id).where(ReportFieldMapping.profile_id == profile.id,
                                                ReportFieldMapping.target_field == target)
        )).scalars().all()
        if any(str(i) != str(mapping_id) for i in clash):
            errors.append(f"'{target}' is already mapped in this profile.")
    if transform:
        try:
            _validate_transform_chain(transform)
        except AppError as exc:
            errors.append(exc.message)

    spec = await _spec_field(session, profile, target) if target else None
    if target and spec is None:
        warnings.append(f"'{target}' isn't a field of the specification this return is checked "
                        f"against ({await _spec_label(session, profile)}).")

    key = custom_key(src)
    attribute = None
    if key is not None:
        attribute = (await _fields_by_key(session, [key])).get(key)
        reason = _obsolete_reason(key, attribute)
        if reason:
            errors.append(reason + " Only an active attribute can be mapped.")
        else:
            if attribute.status == CustomStatus.REVIEW:
                warnings.append(f"'{attribute.label}' is under review and may be retired.")
            if spec and spec.get("allowed") and attribute.data_type != "code":
                warnings.append(f"{target} is a coded field ({len(spec['allowed'])} allowed values) but "
                                f"'{attribute.label}' is a {attribute.data_type} attribute.")
            from app.modules.student_record.custom_fields import CustomFieldService

            latest = (await CustomFieldService(session).latest_assessments([attribute.id])).get(attribute.id)
            hesa = ((latest.result or {}).get("hesa") or {}).get("match") if latest else None
            if hesa and hesa.get("pack") == profile.code and hesa.get("field") and target and hesa["field"] != target:
                warnings.append(f"'{attribute.label}' was requested for HESA {hesa['field']}, not {target}.")
    elif src and src not in _CORE_PATHS:
        warnings.append(f"'{src}' isn't in the record catalogue; it will read blank.")
    elif not src:
        warnings.append("No source yet — the field will be empty unless it has a default.")

    return {
        "valid": not errors, "errors": errors, "warnings": warnings,
        "spec": ({"field": spec.get("field"), "description": spec.get("description", ""),
                  "allowed": list(spec.get("allowed") or []), "required": spec.get("required", True)}
                 if spec else None),
        "customAttribute": ({"id": str(attribute.id), "key": attribute.key, "label": attribute.label,
                             "status": attribute.status, "dataType": attribute.data_type}
                            if attribute else None),
    }


async def profile_record_schema(session: AsyncSession, profile: ReportProfile) -> dict:
    """The mapping picker for one profile: the core catalogue plus live custom attributes,
    annotated with type, status, HESA relevance to this return and current use here."""
    from app.modules.exports.spec_resolver import resolve_fields
    from app.modules.student_record.custom_fields import CustomFieldService

    body = as_dict()
    live = list((await session.execute(
        select(StudentCustomField).where(StudentCustomField.status.in_(CustomStatus.LIVE))
        .order_by(StudentCustomField.label)
    )).scalars().all())
    spec_fields = {f.get("field") for f in await resolve_fields(session, profile.code, profile.academic_year)}
    mapped_as: dict[str, list[str]] = {}
    for m in (await session.execute(
        select(ReportFieldMapping).where(ReportFieldMapping.profile_id == profile.id)
    )).scalars().all():
        k = custom_key(m.source_expression)
        if k:
            mapped_as.setdefault(k, []).append(m.target_field)
    latest = await CustomFieldService(session).latest_assessments(f.id for f in live)

    fields = []
    for f in live:
        hesa = (((latest.get(f.id).result or {}).get("hesa") or {}).get("match")) if latest.get(f.id) else None
        relevant = bool(hesa and hesa.get("pack") == profile.code and hesa.get("field") in spec_fields)
        fields.append({
            "path": f"custom.{f.key}", "label": f"Custom · {f.label}", "type": f.data_type,
            "hint": f.reason, "nullable": True, "status": f.status,
            "hesaField": hesa.get("field") if hesa else None, "hesaRelevant": relevant,
            "mappedAs": mapped_as.get(f.key, []),
        })
    # Most relevant first: requested for a field of this return, then not yet mapped here.
    fields.sort(key=lambda x: (not x["hesaRelevant"], bool(x["mappedAs"]), x["label"]))
    if fields:
        body["groups"].append({
            "root": "custom", "label": "Custom attributes",
            "description": "Approved, active attributes captured for statutory returns.",
            "fields": fields,
        })
        body["paths"].extend(x["path"] for x in fields)
    body["profile"] = {"id": str(profile.id), "code": profile.code, "academicYear": profile.academic_year}
    return body


async def profile_custom_attributes(session: AsyncSession, profile: ReportProfile) -> dict:
    """The custom attributes this profile uses (with any that are obsolete), and how many live
    ones exist that it doesn't use."""
    deps = [d for d in await profile_dependencies(session, profile) if d["kind"] == "custom"]
    used_keys = {d["customKey"] for d in deps}
    live = (await session.execute(
        select(StudentCustomField.key).where(StudentCustomField.status.in_(CustomStatus.LIVE))
    )).scalars().all()
    return {
        "used": deps,
        "obsoleteCount": sum(1 for d in deps if d["obsolete"]),
        "unusedLive": sorted(k for k in live if k not in used_keys),
    }
