"""Custom attribute governance, Phase 6 — is an active attribute still needed?

Signals, per attribute (all computed in a handful of grouped queries for the whole catalogue):

- **mappings** (strong) — which returns read it; a mapping in a live (active, not signed-off)
  return *protects* the attribute: it is never proposed for review.
- **export use** (strong) — when a return last read it for real (generated, downloaded, signed
  off), recorded by :func:`record_usage`.
- **fill rate** (supporting) — the share of currently-studying students with a value.
- **freshness** (supporting) — the last value change, export, or decision.
- **HESA requirement** (strong) — the HESA field it was requested for is still in the newest
  effective specification of that return.

Review rules (deterministic; plan Phase 6):

- live mapping                       → protected, never a candidate
- no mapping and fill rate below 10% → review
- nothing for a reporting cycle      → review (no value change, export or decision in 365 days)
- HESA field removed from the spec   → review

Nothing here changes an attribute. A candidate is a suggestion; a person puts it under review
(Phase 3) and an approver decides.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.student_record.models import (
    Student,
    StudentCustomField,
    StudentCustomFieldUsage,
    StudentCustomValue,
)

LOW_FILL_RATE = 0.10
REPORTING_CYCLE = timedelta(days=365)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def record_usage(session: AsyncSession, *, keys, profile, purpose: str, row_count: int) -> int:
    """Note that ``profile`` read these custom attributes for real. Adds rows; the caller commits."""
    keys = [k for k in (keys or []) if k]
    if not keys:
        return 0
    ids = (await session.execute(
        select(StudentCustomField.id).where(StudentCustomField.key.in_(keys))
    )).scalars().all()
    pid = profile.get("id") if isinstance(profile, dict) else profile.id
    code = profile.get("code") if isinstance(profile, dict) else profile.code
    year = profile.get("academicYear") if isinstance(profile, dict) else profile.academic_year
    for fid in ids:
        session.add(StudentCustomFieldUsage(
            custom_field_id=fid, profile_id=uuid.UUID(str(pid)) if pid else None,
            profile_code=code, academic_year=year, purpose=purpose, row_count=row_count,
        ))
    return len(ids)


async def _current_hesa_fields(session: AsyncSession) -> dict[str, tuple[str, set[str]]]:
    """For each spec pack: (label of its newest effective version, the field codes in it)."""
    from app.modules.exports.spec_resolver import resolve_list_packs, resolve_pack

    newest: dict[str, dict] = {}
    for p in await resolve_list_packs(session):
        if p["code"] not in newest or p.get("academicYear", "") > newest[p["code"]].get("academicYear", ""):
            newest[p["code"]] = p
    out = {}
    for code, p in newest.items():
        pack = await resolve_pack(session, p["key"])
        if pack:
            out[code] = (f"{code} {pack['academic_year']} v{pack['version']}",
                         {f.get("field") for f in pack.get("fields", [])})
    return out


async def health(session: AsyncSession, fields, *, now: datetime | None = None) -> dict:
    """Signals and the review recommendation for each attribute in ``fields``."""
    from app.modules.exports.models import ReportFieldMapping, ReportProfile
    from app.modules.student_record.constants import STUDYING_STATUSES
    from app.modules.student_record.custom_fields import CustomFieldService, Status

    fields = list(fields)
    if not fields:
        return {}
    now = now or datetime.now(timezone.utc)
    ids = [f.id for f in fields]
    by_key = {f.key: f for f in fields}

    studying = int((await session.execute(
        select(func.count()).select_from(Student).where(Student.status.in_(list(STUDYING_STATUSES)))
    )).scalar_one())
    filled = dict((await session.execute(
        select(StudentCustomValue.custom_field_id, func.count())
        .join(Student, Student.id == StudentCustomValue.student_id)
        .where(StudentCustomValue.custom_field_id.in_(ids), Student.status.in_(list(STUDYING_STATUSES)),
               StudentCustomValue.value.is_not(None), StudentCustomValue.value != "")
        .group_by(StudentCustomValue.custom_field_id)
    )).all())
    last_value = dict((await session.execute(
        select(StudentCustomValue.custom_field_id, func.max(StudentCustomValue.updated_at))
        .where(StudentCustomValue.custom_field_id.in_(ids)).group_by(StudentCustomValue.custom_field_id)
    )).all())
    use = {fid: (last, n) for fid, last, n in (await session.execute(
        select(StudentCustomFieldUsage.custom_field_id, func.max(StudentCustomFieldUsage.used_at), func.count())
        .where(StudentCustomFieldUsage.custom_field_id.in_(ids)).group_by(StudentCustomFieldUsage.custom_field_id)
    )).all()}
    mappings: dict[str, list[dict]] = {}
    for m, p in (await session.execute(
        select(ReportFieldMapping, ReportProfile)
        .join(ReportProfile, ReportProfile.id == ReportFieldMapping.profile_id)
        .where(ReportFieldMapping.source_expression.in_([f"custom.{k}" for k in by_key]))
    )).all():
        mappings.setdefault(m.source_expression[len("custom."):], []).append({
            "profileId": str(p.id), "profileCode": p.code, "academicYear": p.academic_year,
            "targetField": m.target_field, "signedOff": p.signed_off_at is not None,
            "live": bool(p.is_active) and p.signed_off_at is None,
        })
    latest = await CustomFieldService(session).latest_assessments(ids)
    specs = await _current_hesa_fields(session)

    out = {}
    for f in fields:
        maps = mappings.get(f.key, [])
        live_maps = [m for m in maps if m["live"]]
        n_filled = int(filled.get(f.id, 0))
        fill_rate = round(n_filled / studying, 3) if studying else 0.0
        last_used, use_count = use.get(f.id, (None, 0))
        activity = [d for d in (_aware(last_value.get(f.id)), _aware(last_used), _aware(f.decided_at),
                                _aware(f.created_at)) if d]
        last_activity = max(activity) if activity else None

        hesa = (((latest.get(f.id).result or {}).get("hesa") or {}).get("match")) if latest.get(f.id) else None
        if not hesa:
            hesa_state, hesa_spec = "unknown", None
        else:
            spec_label, current = specs.get(hesa.get("pack"), (None, None))
            hesa_spec = spec_label
            hesa_state = "unknown" if current is None else ("present" if hesa["field"] in current else "removed")

        reasons = []
        if not maps and fill_rate < LOW_FILL_RATE:
            reasons.append(f"Not mapped in any return and only {fill_rate:.0%} of current students have a value.")
        if last_activity is not None and now - last_activity > REPORTING_CYCLE:
            reasons.append(f"Nothing has happened for over a reporting cycle (last activity "
                           f"{last_activity.date().isoformat()}).")
        if hesa_state == "removed":
            reasons.append(f"HESA {hesa['field']} is no longer in {hesa_spec}.")
        protected = bool(live_maps)
        candidate = f.status == Status.ACTIVE and bool(reasons) and not protected
        out[f.id] = {
            "mappings": maps,
            "liveMappingCount": len(live_maps),
            "filledCount": n_filled,
            "currentStudents": studying,
            "fillRate": fill_rate,
            "lastValueUpdate": _aware(last_value.get(f.id)).isoformat() if last_value.get(f.id) else None,
            "lastUsed": _aware(last_used).isoformat() if last_used else None,
            "useCount": int(use_count),
            "lastActivity": last_activity.isoformat() if last_activity else None,
            "hesa": {"field": hesa.get("field") if hesa else None, "state": hesa_state, "specification": hesa_spec},
            "protected": protected,
            "reasons": reasons,
            "reviewCandidate": candidate,
            "recommendation": ("under review" if f.status == Status.REVIEW
                               else "review" if candidate
                               else "keep — mapped in a live return" if protected
                               else "keep"),
        }
    return out


async def usage_detail(session: AsyncSession, field: StudentCustomField, *, limit: int = 20) -> dict:
    """When and where returns read this attribute: totals per return, and the latest uses."""
    rows = (await session.execute(
        select(StudentCustomFieldUsage.profile_code, StudentCustomFieldUsage.academic_year,
               StudentCustomFieldUsage.purpose, func.count(), func.max(StudentCustomFieldUsage.used_at))
        .where(StudentCustomFieldUsage.custom_field_id == field.id)
        .group_by(StudentCustomFieldUsage.profile_code, StudentCustomFieldUsage.academic_year,
                  StudentCustomFieldUsage.purpose)
    )).all()
    recent = (await session.execute(
        select(StudentCustomFieldUsage).where(StudentCustomFieldUsage.custom_field_id == field.id)
        .order_by(StudentCustomFieldUsage.used_at.desc()).limit(limit)
    )).scalars().all()
    return {
        "byReturn": [{"profileCode": c, "academicYear": y, "purpose": p, "count": n,
                      "lastUsed": _aware(last).isoformat() if last else None} for c, y, p, n, last in rows],
        "recent": [{"profileCode": u.profile_code, "academicYear": u.academic_year, "purpose": u.purpose,
                    "rowCount": u.row_count, "at": _aware(u.used_at).isoformat()} for u in recent],
    }
