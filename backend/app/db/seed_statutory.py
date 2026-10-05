"""Idempotent statutory seed, loaded from app/db/data/statutory_seed.json.

Recreates this environment's statutory configuration on a box that has none: DB spec-pack versions,
report profiles + their field mappings, and admin-defined custom student attributes + per-student
values (matched by student_ref). Profiles are seeded as DRAFT (sign-off is a person's attestation,
never seeded). Custom values whose student_ref isn't present are skipped with a note.

Run with:  python -m app.db.seed_statutory
Safe to re-run: matched by (pack_code, year, version) / (code, year, version) / key / (field, student);
field mappings are reconciled to the seed. Writes with the same (default) tenant as the base seed.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.db import registry as _registry  # noqa: F401

from app.core.database import SessionFactory
from app.modules.exports.constants import SpecVersionStatus
from app.modules.exports.models import ReportFieldMapping, ReportProfile, StatutorySpecVersion
from app.modules.student_record.models import Student, StudentCustomField, StudentCustomValue

DATA = Path(__file__).parent / "data" / "statutory_seed.json"


async def _spec_version(session, v: dict) -> None:
    row = (await session.execute(
        select(StatutorySpecVersion).where(
            StatutorySpecVersion.pack_code == v["pack_code"],
            StatutorySpecVersion.academic_year == v["academic_year"],
            StatutorySpecVersion.version == v["version"],
        )
    )).scalar_one_or_none()
    if row is None:
        row = StatutorySpecVersion(
            pack_code=v["pack_code"], academic_year=v["academic_year"], version=v["version"],
        )
        session.add(row)
    row.name = v["name"]
    row.status = SpecVersionStatus(v.get("status") or "active")
    row.fields = v.get("fields") or []
    row.rules = v.get("rules") or []
    row.disabled_rule_keys = v.get("disabled_rule_keys") or []
    row.source_advisory_id = None   # ids from another DB don't apply here
    row.accepted_by = None
    await session.flush()


async def _profile(session, p: dict) -> None:
    ver = p.get("version") or 1
    prof = (await session.execute(
        select(ReportProfile).where(
            ReportProfile.code == p["code"],
            ReportProfile.academic_year == p["academic_year"],
            ReportProfile.version == ver,
        )
    )).scalar_one_or_none()
    if prof is None:
        prof = ReportProfile(code=p["code"], academic_year=p["academic_year"], version=ver)
        session.add(prof)
    prof.name = p["name"]
    prof.description = p.get("description")
    prof.muted_rule_keys = p.get("muted_rule_keys") or []
    await session.flush()

    # Reconcile field mappings to the seed (authoritative): replace the set for this profile.
    existing = (await session.execute(
        select(ReportFieldMapping).where(ReportFieldMapping.profile_id == prof.id)
    )).scalars().all()
    want = [(f["target_field"], f.get("position") or 0, f.get("source_expression") or "",
             f.get("transform"), f.get("default_value"), bool(f.get("required")),
             tuple(f.get("allowed_values") or [])) for f in p.get("fields", [])]
    have = [(m.target_field, m.position, m.source_expression, m.transform, m.default_value,
             m.required, tuple(m.allowed_values or [])) for m in existing]
    if sorted(have, key=str) != sorted(want, key=str):
        for m in existing:
            await session.delete(m)
        await session.flush()
        for f in p.get("fields", []):
            session.add(ReportFieldMapping(
                profile_id=prof.id, target_field=f["target_field"],
                position=f.get("position") or 0,
                source_expression=f.get("source_expression") or "",
                transform=f.get("transform"), default_value=f.get("default_value"),
                required=bool(f.get("required")), allowed_values=f.get("allowed_values"),
            ))


async def _custom_field(session, c: dict) -> int:
    field = (await session.execute(
        select(StudentCustomField).where(StudentCustomField.key == c["key"])
    )).scalar_one_or_none()
    if field is None:
        field = StudentCustomField(key=c["key"], label=c["label"], data_type=c.get("data_type") or "string",
                                   reason=c.get("reason") or "")
        session.add(field)
    else:
        field.label = c["label"]
        field.data_type = c.get("data_type") or field.data_type
        field.reason = c.get("reason") or field.reason
    await session.flush()

    skipped = 0
    for v in c.get("values", []):
        student = (await session.execute(
            select(Student).where(Student.student_ref == v["student_ref"])
        )).scalar_one_or_none()
        if student is None:
            skipped += 1
            continue
        existing = (await session.execute(
            select(StudentCustomValue).where(
                StudentCustomValue.custom_field_id == field.id,
                StudentCustomValue.student_id == student.id,
            )
        )).scalar_one_or_none()
        if existing is None:
            session.add(StudentCustomValue(
                custom_field_id=field.id, student_id=student.id, value=v.get("value"),
            ))
        else:
            existing.value = v.get("value")
    return skipped


async def main() -> None:
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    async with SessionFactory() as session:
        for v in doc.get("spec_versions", []):
            await _spec_version(session, v)
        for p in doc.get("profiles", []):
            await _profile(session, p)
        skipped = 0
        for c in doc.get("custom_fields", []):
            skipped += await _custom_field(session, c)
        await session.commit()
    msg = (f"Statutory seeded: {len(doc.get('spec_versions', []))} spec version(s), "
           f"{len(doc.get('profiles', []))} profile(s), {len(doc.get('custom_fields', []))} custom field(s).")
    if skipped:
        msg += f" ({skipped} custom value(s) skipped — student_ref not present; seed students first.)"
    print(msg)


if __name__ == "__main__":
    asyncio.run(main())
