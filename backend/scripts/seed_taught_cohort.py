"""Seed a taught (PGT / MSc) programme, its modules/assessments, and a small cohort — ICR G1.

Uses the REAL taught service code paths (not hand-crafted rows), so every enrolment, result,
dissertation and classification is exactly what the running app would produce:

  - TaughtService.create_module / add_assessment  — programme structure
  - TaughtService.enrol                           — module enrolments
  - TaughtService.record_result                   — assessment marks (incl. a resit)
  - TaughtService.upsert_dissertation             — dissertation + mark
  - TaughtService.compute_award                   — credit-weighted classification

Programme: MSc Clinical Oncology (MSC-ONC), 180 credits = 4 x 30-credit taught modules + a
60-credit dissertation. Cohort of 7 gives a full classification spread plus one in-progress
student (no dissertation / award yet).

Idempotent — skips the programme's modules if already defined, and skips any student whose
deterministic demo email already exists. Safe to re-run.

    python -m scripts.seed_taught_cohort
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionFactory
from app.db import registry as _registry  # noqa: F401
from app.modules.person.models import Person
from app.modules.progression.models import MilestoneDefinition
from app.modules.student_record.constants import ProgrammeType, StudentStatus
from app.modules.student_record.models import Programme, Student
from app.modules.taught.constants import AssessmentType
from app.modules.taught.repository import TaughtRepository
from app.modules.taught.service import TaughtService
from app.modules.taught.schemas import (
    AssessmentCreate, DissertationUpsert, EnrolmentCreate, ModuleCreate, ResultRecord,
)

PROGRAMME_CODE = "MSC-ONC"
ACADEMIC_YEAR = "2025/26"

# module code -> (title, credits, [(assessment title, type, weight%)])
MODULES = [
    ("ONC501", "Foundations of Oncology", 30, [
        ("Critical essay", AssessmentType.essay, 40),
        ("Written exam", AssessmentType.exam, 60),
    ]),
    ("ONC502", "Clinical Trials & Statistics", 30, [
        ("Trial protocol coursework", AssessmentType.coursework, 50),
        ("Statistics exam", AssessmentType.exam, 50),
    ]),
    ("ONC503", "Radiotherapy & Imaging", 30, [
        ("Case essay", AssessmentType.essay, 50),
        ("Seminar presentation", AssessmentType.presentation, 50),
    ]),
    ("ONC504", "Molecular Therapeutics", 30, [
        ("Written exam", AssessmentType.exam, 100),
    ]),
]

MILESTONES = [
    ("Induction complete", 30),
    ("Term 1 progress review", 150),
    ("Dissertation proposal approved", 240),
]

# name, target average mark, add a dissertation+award? (in-progress student = False)
COHORT = [
    ("Amara", "Okonkwo", 76, True),
    ("Daniel", "Whitfield", 73, True),
    ("Priya", "Ramaswamy", 66, True),
    ("Thomas", "Berg", 55, True),
    ("Lucia", "Ferrari", 53, True),
    ("Kofi", "Mensah", 46, True),      # a fail — shows the full band range
    ("Sarah", "Lindqvist", 0, False),  # in-progress: enrolled, no marks yet
]

# Deterministic per-assessment offsets around the target, so a module isn't perfectly flat.
_OFFSETS = [3, -2, 1, -3, 2, -1]


async def _get_or_create_programme(s) -> Programme:
    prog = (await s.execute(select(Programme).where(Programme.code == PROGRAMME_CODE))).scalar_one_or_none()
    if prog is None:
        prog = Programme(
            name="MSc Clinical Oncology", code=PROGRAMME_CODE,
            programme_type=ProgrammeType.taught, taught_total_credits=180,
        )
        s.add(prog)
        await s.flush()
        print(f"created programme {prog.code} ({prog.name})")
    elif prog.programme_type != ProgrammeType.taught:
        prog.programme_type = ProgrammeType.taught
        prog.taught_total_credits = 180
        print(f"flipped existing programme {prog.code} to taught")
    # Milestone templates (generic per-programme mechanism — same as research programmes).
    existing_defs = {
        d.name for d in (await s.execute(
            select(MilestoneDefinition).where(MilestoneDefinition.programme_id == prog.id)
        )).scalars().all()
    }
    for name, offset in MILESTONES:
        if name not in existing_defs:
            s.add(MilestoneDefinition(programme_id=prog.id, name=name, due_offset_days=offset))
    await s.commit()
    return prog


async def _ensure_modules(s, prog: Programme) -> None:
    svc = TaughtService(TaughtRepository(s))
    existing = await svc.list_modules(prog.id)
    if existing:
        print(f"programme already has {len(existing)} modules — skipping module creation")
        return
    for code, title, credits, assessments in MODULES:
        m = await svc.create_module(prog.id, ModuleCreate(code=code, title=title, credits=credits))
        for a_title, a_type, weight in assessments:
            await svc.add_assessment(m["id"], AssessmentCreate(
                title=a_title, assessment_type=a_type, weight_pct=Decimal(weight),
            ))
    print(f"created {len(MODULES)} modules with assessments")


async def _seed_students(s, prog: Programme) -> None:
    svc = TaughtService(TaughtRepository(s))
    modules = await svc.list_modules(prog.id)
    start = date(2025, 9, 1)

    for i, (given, family, target, finalise) in enumerate(COHORT):
        email = f"taught.{family.lower()}@oncology.icr.demo"
        if (await s.execute(select(Person).where(Person.email == email))).scalar_one_or_none():
            print(f"  {given} {family} already seeded — skipping")
            continue
        person = Person(given_name=given, family_name=family, email=email)
        s.add(person)
        await s.flush()
        ref = f"PGR-2025-{uuid.uuid4().hex[:6].upper()}"
        student = Student(
            person_id=person.id, student_ref=ref, programme_id=prog.id,
            status=StudentStatus.active, start_date=start,
        )
        s.add(student)
        await s.commit()

        # Enrol on every module; record marks (except the in-progress student, who only has
        # the first two modules marked and no dissertation/award).
        marked_modules = modules if finalise else modules[:2]
        for mi, mod in enumerate(modules):
            enr = await svc.enrol(student.id, EnrolmentCreate(module_id=mod["id"], academic_year=ACADEMIC_YEAR))
            if mod not in marked_modules:
                continue
            for ai, a in enumerate(mod["assessments"]):
                mark = max(0, min(100, target + _OFFSETS[(mi + ai) % len(_OFFSETS)]))
                await svc.record_result(enr["id"], ResultRecord(
                    assessment_id=a["id"], mark=Decimal(mark),
                    submitted_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
                ), user_id=None)

        if finalise:
            await svc.upsert_dissertation(student.id, DissertationUpsert(
                title=f"{family} dissertation on targeted oncology therapy",
                submitted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                mark=Decimal(max(0, min(100, target - 1))),
            ))
            award = await svc.compute_award(student.id, user_id=None)
            print(f"  {given} {family} ({ref}): {award['classification']} "
                  f"(final {award['final_mark']}, {award['credits_achieved']} cr)")
        else:
            print(f"  {given} {family} ({ref}): in progress (2 of {len(modules)} modules marked, no award)")

    # One resit example: give the failing student a better second attempt on one assessment.
    fail_person = (await s.execute(
        select(Person).where(Person.email == "taught.mensah@oncology.icr.demo")
    )).scalar_one_or_none()
    if fail_person:
        student = (await s.execute(select(Student).where(Student.person_id == fail_person.id))).scalar_one_or_none()
        if student:
            enrolments = await svc.repo.enrolments_for_student(student.id)
            if enrolments:
                mod0 = await svc.repo.get_module(enrolments[0].module_id)
                first_asmt = mod0.assessments[0]
                already_resat = any(r.is_resit for e in enrolments for r in e.results)
                if not already_resat:
                    await svc.record_result(enrolments[0].id, ResultRecord(
                        assessment_id=first_asmt.id, mark=Decimal("50"), is_resit=True,
                        submitted_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
                    ), user_id=None)
                    await svc.compute_award(student.id, user_id=None)
                    print("  recorded a resit (best attempt) for Kofi Mensah and recomputed the award")


async def main() -> None:
    async with SessionFactory() as s:
        prog = await _get_or_create_programme(s)
        await _ensure_modules(s, prog)
        await _seed_students(s, prog)
    print("done.")


if __name__ == "__main__":
    asyncio.run(main())
