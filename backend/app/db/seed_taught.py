"""Idempotent taught-programme seed, loaded from app/db/data/taught_seed.json.

That JSON is a real export of this environment's taught programmes (MSc Clinical Oncology and
Msc Clinical Neurology) with their modules, assessments, students and module enrolments, produced
by `python -m app.db.export_taught`. Running this seed recreates the exact same content on a box
that has no taught data (e.g. the VM).

Run with:   python -m app.db.seed_taught
Safe to re-run: rows are matched by code / student_ref / (module code) and reused, never duplicated.
Writes with the same (default) tenant as the base seed, so the demo admin sees them.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

# Register every model on Base.metadata before any ORM work (see the note in app/db/seed.py).
from app.db import registry as _registry  # noqa: F401

from app.core.database import SessionFactory
from app.modules.person.models import Person
from app.modules.student_record.constants import ProgrammeType, StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student
from app.modules.taught.constants import AssessmentType, ModuleEnrolmentStatus, ModuleOutcome
from app.modules.taught.models import ModuleAssessment, ModuleEnrolment, TaughtModule

DATA = Path(__file__).parent / "data" / "taught_seed.json"


def _date(v):
    return date.fromisoformat(v) if v else None


def _dec(v, default=None):
    return Decimal(str(v)) if v not in (None, "") else default


async def _programme(session, p: dict) -> Programme:
    prog = (await session.execute(
        select(Programme).where(Programme.code == p["code"])
    )).scalar_one_or_none()
    if prog is None:
        prog = Programme(name=p["name"], code=p["code"])
        session.add(prog)
    prog.programme_type = ProgrammeType(p.get("programme_type") or "taught")
    prog.taught_total_credits = p.get("taught_total_credits")
    prog.duration_months = p.get("duration_months")
    if p.get("grading_policy") is not None:
        prog.grading_policy = p["grading_policy"]
    await session.flush()
    return prog


async def _module(session, programme_id, m: dict) -> TaughtModule:
    mod = (await session.execute(
        select(TaughtModule).where(
            TaughtModule.programme_id == programme_id, TaughtModule.code == m["code"],
        )
    )).scalar_one_or_none()
    if mod is None:
        mod = TaughtModule(
            programme_id=programme_id, code=m["code"], title=m["title"],
            credits=m.get("credits") or 0, level=m.get("level") or 7,
            is_core=bool(m.get("is_core", True)), term=m.get("term"),
        )
        session.add(mod)
        await session.flush()
        for a in m.get("assessments", []):
            asmt = ModuleAssessment(
                module_id=mod.id, title=a["title"],
                assessment_type=AssessmentType(a["assessment_type"]),
                weight_pct=_dec(a.get("weight_pct"), Decimal("100.00")),
                pass_mark=_dec(a.get("pass_mark"), Decimal("50.00")),
            )
            if a.get("resit_cap") is not None and hasattr(asmt, "resit_cap"):
                asmt.resit_cap = _dec(a["resit_cap"])
            if a.get("resit_allowed") is not None and hasattr(asmt, "resit_allowed"):
                asmt.resit_allowed = bool(a["resit_allowed"])
            session.add(asmt)
    return mod


async def _student(session, s: dict, programme_id) -> Student:
    student = (await session.execute(
        select(Student).where(Student.student_ref == s["ref"])
    )).scalar_one_or_none()
    if student is not None:
        return student
    # Reuse a person with the same email if one exists (older imports left some with no email).
    person = None
    if s.get("email"):
        person = (await session.execute(
            select(Person).where(Person.email == s["email"])
        )).scalar_one_or_none()
    if person is None:
        person = Person(
            given_name=s["given"], family_name=s["family"],
            email=s.get("email"), nationality=s.get("nationality"),
            date_of_birth=_date(s.get("date_of_birth")),
        )
        session.add(person)
        await session.flush()
    student = Student(
        person_id=person.id, student_ref=s["ref"], programme_id=programme_id,
        start_date=_date(s.get("start_date")),
        expected_end_date=_date(s.get("expected_end_date")),
        original_expected_end_date=_date(s.get("original_expected_end_date")),
        study_mode=StudyMode(s.get("study_mode") or "full_time"),
        status=StudentStatus(s.get("status") or "registered"),
    )
    session.add(student)
    await session.flush()
    return student


async def _enrol(session, student_id, module_id, e: dict) -> None:
    exists = (await session.execute(
        select(ModuleEnrolment).where(
            ModuleEnrolment.student_id == student_id, ModuleEnrolment.module_id == module_id,
        )
    )).scalar_one_or_none()
    if exists is not None:
        return
    session.add(ModuleEnrolment(
        student_id=student_id, module_id=module_id,
        academic_year=e.get("academic_year") or "2026/27",
        status=ModuleEnrolmentStatus(e.get("status") or "enrolled"),
        outcome=ModuleOutcome(e.get("outcome") or "pending"),
        final_mark=_dec(e.get("final_mark")),
        credits_awarded=e.get("credits_awarded"),
        condoned=bool(e.get("condoned", False)),
    ))


async def main() -> None:
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    async with SessionFactory() as session:
        summary = []
        for p in doc["programmes"]:
            prog = await _programme(session, p)
            mod_by_code = {}
            for m in p.get("modules", []):
                mod_by_code[m["code"]] = await _module(session, prog.id, m)
            n_students = 0
            for s in p.get("students", []):
                student = await _student(session, s, prog.id)
                n_students += 1
                for e in s.get("enrolments", []):
                    mod = mod_by_code.get(e.get("module_code"))
                    if mod is not None:
                        await _enrol(session, student.id, mod.id, e)
            summary.append(f"{prog.code}: {len(mod_by_code)} modules, {n_students} students")
        await session.commit()
    print("Taught data seeded (from taught_seed.json): " + "; ".join(summary))


if __name__ == "__main__":
    asyncio.run(main())
