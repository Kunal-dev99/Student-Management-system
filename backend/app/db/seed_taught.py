"""Idempotent taught-programme demo seed (ICR G1).

Adds two TAUGHT programmes, their core modules + assessments, and two students enrolled on them,
so the taught surface (Programmes -> Modules, the taught student panels, the taught record) has
real content on a box that only has research data.

Run with:   python -m app.db.seed_taught
Safe to re-run: existing rows (matched by code / student_ref / email) are reused, never duplicated.
It writes with the same (default) tenant as the base seed, so the demo admin sees them.
"""
from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

from sqlalchemy import select

# Register every model on Base.metadata before any ORM work (see the note in app/db/seed.py).
from app.db import registry as _registry  # noqa: F401

from app.core.database import SessionFactory
from app.modules.person.models import Person
from app.modules.student_record.constants import ProgrammeType, StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student
from app.modules.taught.constants import AssessmentType, ModuleEnrolmentStatus, ModuleOutcome
from app.modules.taught.models import ModuleAssessment, ModuleEnrolment, TaughtModule

ACADEMIC_YEAR = "2026/27"
START = date(2026, 10, 1)
END = date(2027, 9, 30)

# programme -> its core modules -> each module's assessments (weights within a module sum to 100).
TAUGHT: list[dict] = [
    {
        "code": "MSC-DS", "name": "MSc Data Science",
        "student": {"given": "Aisha", "family": "Khan", "email": "aisha.khan@example.ac.uk",
                    "ref": "MSC-DS-2601", "nationality": "British"},
        "modules": [
            {"code": "DS701", "title": "Foundations of Machine Learning", "credits": 30,
             "assessments": [("Coursework", AssessmentType.coursework, 50, 50),
                             ("Written exam", AssessmentType.exam, 50, 50)]},
            {"code": "DS702", "title": "Statistical Inference", "credits": 30,
             "assessments": [("Problem sets", AssessmentType.coursework, 40, 50),
                             ("Exam", AssessmentType.exam, 60, 50)]},
        ],
    },
    {
        "code": "MSC-PH", "name": "MSc Public Health",
        "student": {"given": "Marco", "family": "Rossi", "email": "marco.rossi@example.ac.uk",
                    "ref": "MSC-PH-2601", "nationality": "Italian"},
        "modules": [
            {"code": "PH701", "title": "Epidemiology", "credits": 30,
             "assessments": [("Essay", AssessmentType.essay, 40, 50),
                             ("Exam", AssessmentType.exam, 60, 50)]},
            {"code": "PH702", "title": "Health Systems & Policy", "credits": 30,
             "assessments": [("Policy brief", AssessmentType.coursework, 100, 50)]},
        ],
    },
]


async def _programme(session, code: str, name: str) -> Programme:
    prog = (await session.execute(
        select(Programme).where(Programme.code == code)
    )).scalar_one_or_none()
    if prog is None:
        prog = Programme(name=name, code=code, programme_type=ProgrammeType.taught,
                         taught_total_credits=180, duration_months=12)
        session.add(prog)
        await session.flush()
    elif prog.programme_type is not ProgrammeType.taught:
        prog.programme_type = ProgrammeType.taught
        prog.taught_total_credits = prog.taught_total_credits or 180
    return prog


async def _module(session, programme_id, m: dict) -> TaughtModule:
    mod = (await session.execute(
        select(TaughtModule).where(
            TaughtModule.programme_id == programme_id, TaughtModule.code == m["code"],
        )
    )).scalar_one_or_none()
    if mod is None:
        mod = TaughtModule(programme_id=programme_id, code=m["code"], title=m["title"],
                           credits=m["credits"], level=7, is_core=True, term="Autumn 2026")
        session.add(mod)
        await session.flush()
        for title, atype, weight, passmark in m["assessments"]:
            session.add(ModuleAssessment(
                module_id=mod.id, title=title, assessment_type=atype,
                weight_pct=Decimal(str(weight)), pass_mark=Decimal(str(passmark)),
            ))
    return mod


async def _student(session, s: dict, programme_id) -> Student:
    person = (await session.execute(
        select(Person).where(Person.email == s["email"])
    )).scalar_one_or_none()
    if person is None:
        person = Person(given_name=s["given"], family_name=s["family"],
                        email=s["email"], nationality=s["nationality"])
        session.add(person)
        await session.flush()
    student = (await session.execute(
        select(Student).where(Student.student_ref == s["ref"])
    )).scalar_one_or_none()
    if student is None:
        student = Student(
            person_id=person.id, student_ref=s["ref"], programme_id=programme_id,
            start_date=START, expected_end_date=END, original_expected_end_date=END,
            study_mode=StudyMode.full_time, status=StudentStatus.registered,
        )
        session.add(student)
        await session.flush()
    return student


async def _enrol(session, student_id, module_id) -> None:
    exists = (await session.execute(
        select(ModuleEnrolment).where(
            ModuleEnrolment.student_id == student_id, ModuleEnrolment.module_id == module_id,
        )
    )).scalar_one_or_none()
    if exists is None:
        session.add(ModuleEnrolment(
            student_id=student_id, module_id=module_id, academic_year=ACADEMIC_YEAR,
            status=ModuleEnrolmentStatus.enrolled, outcome=ModuleOutcome.pending,
        ))


async def main() -> None:
    async with SessionFactory() as session:
        for p in TAUGHT:
            prog = await _programme(session, p["code"], p["name"])
            modules = [await _module(session, prog.id, m) for m in p["modules"]]
            student = await _student(session, p["student"], prog.id)
            for mod in modules:
                await _enrol(session, student.id, mod.id)
        await session.commit()
    print(
        "Taught demo seeded: MSc Data Science (MSC-DS) + MSc Public Health (MSC-PH), "
        "each with 2 core modules + assessments and 1 enrolled student "
        "(Aisha Khan MSC-DS-2601, Marco Rossi MSC-PH-2601)."
    )


if __name__ == "__main__":
    asyncio.run(main())
