"""Export the real taught programmes (+ modules, assessments, students, enrolments) from THIS
database into app/db/data/taught_seed.json, so seed_taught.py can recreate the exact same content
on another box (e.g. the VM).

Run with:   python -m app.db.export_taught            (defaults: MSC-ONC, NE-001)
            python -m app.db.export_taught MSC-ONC     (specific codes)

Idempotent-friendly: the JSON is keyed by stable codes/refs; seed_taught.py matches on them.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.db import registry as _registry  # noqa: F401
from app.core.database import SessionFactory
from app.modules.person.models import Person
from app.modules.student_record.models import Programme, Student
from app.modules.taught.models import ModuleAssessment, ModuleEnrolment, TaughtModule

DEFAULT_CODES = ["MSC-ONC", "NE-001"]
OUT = Path(__file__).parent / "data" / "taught_seed.json"


def _ev(v):
    """Enum -> its value; date -> isoformat; Decimal -> str; else as-is."""
    if v is None:
        return None
    if hasattr(v, "value"):
        return v.value
    if hasattr(v, "isoformat"):
        return v.isoformat()
    from decimal import Decimal
    if isinstance(v, Decimal):
        return str(v)
    return v


async def main(codes: list[str]) -> None:
    async with SessionFactory() as s:
        programmes = []
        for code in codes:
            prog = (await s.execute(select(Programme).where(Programme.code == code))).scalar_one_or_none()
            if prog is None:
                print(f"  (skip) no programme with code {code}")
                continue

            mods = (await s.execute(
                select(TaughtModule).where(TaughtModule.programme_id == prog.id)
                .order_by(TaughtModule.code)
            )).scalars().all()
            mod_by_id = {m.id: m for m in mods}
            modules = []
            for m in mods:
                asmts = (await s.execute(
                    select(ModuleAssessment).where(ModuleAssessment.module_id == m.id)
                )).scalars().all()
                modules.append({
                    "code": m.code, "title": m.title, "credits": m.credits,
                    "level": m.level, "is_core": m.is_core, "term": m.term,
                    "assessments": [{
                        "title": a.title, "assessment_type": _ev(a.assessment_type),
                        "weight_pct": _ev(a.weight_pct), "pass_mark": _ev(a.pass_mark),
                        "resit_cap": _ev(getattr(a, "resit_cap", None)),
                        "resit_allowed": getattr(a, "resit_allowed", None),
                    } for a in asmts],
                })

            students = []
            rows = (await s.execute(
                select(Student, Person).join(Person, Person.id == Student.person_id)
                .where(Student.programme_id == prog.id).order_by(Student.student_ref)
            )).all()
            for st, person in rows:
                enrs = (await s.execute(
                    select(ModuleEnrolment).where(ModuleEnrolment.student_id == st.id)
                )).scalars().all()
                students.append({
                    "ref": st.student_ref,
                    "given": person.given_name, "family": person.family_name,
                    "email": person.email, "nationality": person.nationality,
                    "date_of_birth": _ev(getattr(person, "date_of_birth", None)),
                    "start_date": _ev(st.start_date),
                    "expected_end_date": _ev(st.expected_end_date),
                    "original_expected_end_date": _ev(st.original_expected_end_date),
                    "study_mode": _ev(st.study_mode), "status": _ev(st.status),
                    "enrolments": [{
                        "module_code": mod_by_id[e.module_id].code if e.module_id in mod_by_id else None,
                        "academic_year": e.academic_year,
                        "status": _ev(e.status), "outcome": _ev(e.outcome),
                        "final_mark": _ev(e.final_mark), "credits_awarded": e.credits_awarded,
                        "condoned": e.condoned,
                    } for e in enrs if e.module_id in mod_by_id],
                })

            programmes.append({
                "code": prog.code, "name": prog.name,
                "programme_type": _ev(prog.programme_type),
                "taught_total_credits": prog.taught_total_credits,
                "duration_months": prog.duration_months,
                "grading_policy": prog.grading_policy,
                "modules": modules, "students": students,
            })
            print(f"  {prog.code}: {len(modules)} modules, {len(students)} students")

        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"programmes": programmes}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {OUT} ({len(programmes)} programme(s)).")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or DEFAULT_CODES))
