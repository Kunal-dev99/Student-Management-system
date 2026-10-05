"""Export this environment's statutory configuration to app/db/data/statutory_seed.json, so
seed_statutory.py can recreate it exactly on another box (e.g. the VM).

Covers: DB spec-pack versions (StatutorySpecVersion), report profiles + their field mappings, and
admin-defined custom student attributes + their per-student values (keyed by student_ref, since ids
differ across databases). Advisory ingest history is intentionally NOT exported (it's audit trail,
regenerated when a Registry owner ingests).

Run with:  python -m app.db.export_statutory
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.db import registry as _registry  # noqa: F401
from app.core.database import SessionFactory
from app.core.tenant_context import system_scope  # T1: cross-tenant tool
from app.modules.exports.models import ReportFieldMapping, ReportProfile, StatutorySpecVersion
from app.modules.student_record.models import Student, StudentCustomField, StudentCustomValue

OUT = Path(__file__).parent / "data" / "statutory_seed.json"


def _ev(v):
    if v is None:
        return None
    if hasattr(v, "value"):
        return v.value
    return v


async def main() -> None:
    async with system_scope(), SessionFactory() as s:
        spec_versions = []
        for v in (await s.execute(
            select(StatutorySpecVersion).order_by(
                StatutorySpecVersion.pack_code, StatutorySpecVersion.academic_year,
                StatutorySpecVersion.version,
            )
        )).scalars().all():
            spec_versions.append({
                "pack_code": v.pack_code, "academic_year": v.academic_year, "version": v.version,
                "name": v.name, "status": _ev(v.status),
                "fields": v.fields or [], "rules": v.rules or [],
                "disabled_rule_keys": v.disabled_rule_keys or [],
            })

        profiles = []
        for p in (await s.execute(
            select(ReportProfile).order_by(ReportProfile.code, ReportProfile.academic_year)
        )).scalars().all():
            maps = (await s.execute(
                select(ReportFieldMapping).where(ReportFieldMapping.profile_id == p.id)
                .order_by(ReportFieldMapping.position, ReportFieldMapping.target_field)
            )).scalars().all()
            profiles.append({
                "code": p.code, "name": p.name, "academic_year": p.academic_year,
                "version": p.version, "description": p.description,
                "muted_rule_keys": p.muted_rule_keys or [],
                "fields": [{
                    "target_field": m.target_field, "position": m.position,
                    "source_expression": m.source_expression, "transform": m.transform,
                    "default_value": m.default_value, "required": m.required,
                    "allowed_values": m.allowed_values,
                } for m in maps],
            })

        custom_fields = []
        for f in (await s.execute(
            select(StudentCustomField).order_by(StudentCustomField.key)
        )).scalars().all():
            vals = (await s.execute(
                select(StudentCustomValue, Student.student_ref)
                .join(Student, Student.id == StudentCustomValue.student_id)
                .where(StudentCustomValue.custom_field_id == f.id)
            )).all()
            custom_fields.append({
                "key": f.key, "label": f.label, "data_type": f.data_type, "reason": f.reason,
                "values": [{"student_ref": ref, "value": cv.value} for cv, ref in vals],
            })

        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            json.dumps({
                "spec_versions": spec_versions, "profiles": profiles, "custom_fields": custom_fields,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(
            f"Wrote {OUT}: {len(spec_versions)} spec version(s), {len(profiles)} profile(s) "
            f"({sum(len(p['fields']) for p in profiles)} mappings), {len(custom_fields)} custom field(s)."
        )


if __name__ == "__main__":
    asyncio.run(main())
