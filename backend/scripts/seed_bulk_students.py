"""Bulk ICR student population — 300 students spread across the real pipeline stages.

Extends the small hand-curated cohort from `seed_icr_cohort.py` (14 students) into a
realistic-scale population for load-testing the UI, Weekly Review Queue, Pattern Lab,
and the AI intelligence layer against something bigger than a handful of rows.

Distribution (out of 300):
  - 5 fully completed through to Alumni (thesis approved, completion graduated,
    award published, PersonRelationship flipped to alumni) — with a thesis document
    and a certificate document attached.
  - ~20 on_leave / suspended (realistic exceptions)
  - ~15 withdrawn
  - the rest active/registered, spread across the pipeline from month 1 to month 50
    so milestones land at every stage (not started / due / decided).

Every student gets at least one attached document (a progress-report placeholder)
via the real object store (app/core/storage.py) — not fabricated metadata pointing
nowhere; `Document.open()` will actually return real bytes for these rows.

Requires `scripts/seed_icr.py` to have already run (ICR-PHD / ICR-MDRES programmes
and funders). Idempotent by student_ref prefix — safe to re-run; already-created
students in the BULK-* range are skipped.

    python -m scripts.seed_icr            (if not already run)
    python -m scripts.seed_bulk_students
"""
from __future__ import annotations

import asyncio
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.core.database import SessionFactory
from app.core.storage import get_object_store
# Register every mapper before use — cross-module foreign keys (funding to
# research_award, project to research_opportunity) only resolve once every model
# module is imported, exactly as the Alembic env and seed.py do.
from app.db import registry as _registry  # noqa: F401
from app.modules.completion.constants import CompletionStatus
from app.modules.completion.models import Award, Completion
from app.modules.documents.models import Document
from app.modules.funding.constants import FundingStatus, FundingType
from app.modules.funding.models import FundingSource, FundingArrangement
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.models import Person, PersonRelationship
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone, MilestoneDefinition
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Department, Programme, ResearchProject, Student
from app.modules.supervision.constants import SupervisionStatus, SupervisorRole
from app.modules.supervision.models import SupervisorRelationship
from app.modules.thesis.constants import ThesisStatus
from app.modules.thesis.models import Thesis

random.seed(4200)  # reproducible across re-runs — same 300 people every time

TOTAL_STUDENTS = 300
ALUMNI_COUNT = 5
REF_PREFIX = "BULK"
TODAY = date.today()

FIRST_NAMES = [
    "Amina", "Chen", "Diego", "Fatima", "Giulia", "Hassan", "Ingrid", "Jamal",
    "Keiko", "Liam", "Mei", "Nadia", "Oscar", "Priya", "Quang", "Rosa",
    "Sanjay", "Tanya", "Umar", "Valeria", "Wei", "Ximena", "Yusuf", "Zara",
    "Aiden", "Bianca", "Carlos", "Dana", "Emeka", "Farah", "Gustav", "Hana",
    "Ivan", "Jana", "Kwame", "Lena", "Mohan", "Nina", "Omar", "Paula",
]
LAST_NAMES = [
    "Okonjo", "Chandra", "Kowalski", "Lindgren", "Haddad", "Osei", "Fairbairn",
    "Tanabe", "Rossi", "Adeyemi", "Raghavan", "Whitlock", "Diallo", "Mbeki",
    "Nakamura", "Petrov", "Silva", "Zhao", "Hartley", "Grigsby", "Nguyen",
    "Okafor", "Eriksen", "Abara", "Jensen", "Quirke", "Rahman", "Fontaine",
    "Kimura", "Santos", "Ibrahim", "Novak", "Andersen", "Costa", "Meyer",
]
TOPICS = [
    "Targeting synthetic lethality in homologous recombination-deficient tumours",
    "Single-cell atlas of the tumour immune microenvironment",
    "Radiotherapy response biomarkers across solid tumours",
    "Epigenetic drivers of paediatric and adolescent cancers",
    "Drug-tolerant persister cell states in targeted therapy resistance",
    "Computational modelling of clonal evolution under treatment pressure",
    "Mechanisms of PARP inhibitor and platinum resistance",
    "Mass-spectrometry proteomics of tumour-derived exosomes",
    "Immune evasion mechanisms in advanced solid tumours",
    "CRISPR screens for novel radiosensitiser targets",
    "Circulating tumour DNA as a surgical oncology biomarker",
    "Precision radiotherapy planning using deep learning",
    "Biomarker-guided endocrine therapy sequencing",
    "Liquid biopsy approaches to minimal residual disease detection",
    "Tumour organoid models of chemotherapy response",
]
PI_NAMES = [
    ("Helena", "Vaughan-Price"), ("Idris", "Mahmood"), ("Claire", "Beaumont"),
    ("Andrew", "Fitzgerald"), ("Meera", "Nair"), ("Oliver", "Sandberg"),
    ("Fatoumata", "Diarra"), ("Rajesh", "Iyer"), ("Karin", "Voss"),
    ("Benedict", "Achebe"),
]
CO_SUP_NAMES = [
    ("Yusuf", "Karim"), ("Sinead", "O'Rourke"), ("Wen", "Tao"),
    ("Alicia", "Ferreira"), ("Dmitri", "Volkov"), ("Nour", "Aziz"),
    ("Sven", "Holm"), ("Chidinma", "Eze"),
]


def _clean_email(given: str, family: str, n: int) -> str:
    slug = f"{given}.{family}".lower().replace("'", "").replace(" ", "")
    return f"{slug}.{n}@icr.example.ac.uk"


async def get_or_create_person(s, given: str, family: str, email: str) -> Person:
    p = (await s.execute(select(Person).where(Person.email == email))).scalars().first()
    if p is None:
        p = Person(given_name=given, family_name=family, email=email)
        s.add(p)
        await s.flush()
    return p


def _placeholder_document(owner_type: str, owner_id, doc_type: str, filename: str,
                           body_text: str, uploaded_by=None) -> Document:
    """Write a small real text file through the real object store and return its
    Document metadata row — Document.open() will return real bytes for this row,
    not a checksum pointing at nothing."""
    store = get_object_store()
    data = body_text.encode("utf-8")
    key, checksum, size = store.save(data, suffix=".txt")
    return Document(
        owner_type=owner_type, owner_id=owner_id, doc_type=doc_type,
        filename=filename, content_type="text/plain", size_bytes=size,
        checksum_sha256=checksum, storage_key=key, uploaded_by=uploaded_by,
    )


async def main() -> None:
    async with SessionFactory() as s:
        progs = {p.code: p for p in (await s.execute(
            select(Programme).where(Programme.code.in_(["ICR-PHD", "ICR-MDRES"]))
        )).scalars().all()}
        if not progs:
            raise SystemExit("Run `python -m scripts.seed_icr` first - ICR programmes are missing.")

        dept = (await s.execute(select(Department).where(Department.code == "ICR"))).scalars().first()
        funders = {f.name: f for f in (await s.execute(select(FundingSource))).scalars().all()}
        if not funders:
            raise SystemExit("Run `python -m scripts.seed_icr` first - ICR funders are missing.")
        funder_list = list(funders.values())

        defs_by_prog: dict[str, list[MilestoneDefinition]] = {}
        for code, prog in progs.items():
            defs_by_prog[code] = (await s.execute(
                select(MilestoneDefinition)
                .where(MilestoneDefinition.programme_id == prog.id)
                .order_by(MilestoneDefinition.due_offset_days)
            )).scalars().all()

        existing_count = (await s.execute(
            select(func.count()).select_from(Student)
            .where(Student.student_ref.like(f"{REF_PREFIX}-%"))
        )).scalar_one()
        if existing_count >= TOTAL_STUDENTS:
            print(f"  = {existing_count} {REF_PREFIX}-* students already present - skipped")
            return

        pis = [await get_or_create_person(s, g, f, _clean_email(g, f, i))
               for i, (g, f) in enumerate(PI_NAMES)]
        cos = [await get_or_create_person(s, g, f, _clean_email(g, f, 100 + i))
               for i, (g, f) in enumerate(CO_SUP_NAMES)]
        await s.flush()

        # Deterministic assignment of which sequence numbers become the 5 alumni,
        # spread evenly rather than clustered at the front.
        alumni_indices = set(range(0, TOTAL_STUDENTS, TOTAL_STUDENTS // ALUMNI_COUNT))
        alumni_indices = set(list(alumni_indices)[:ALUMNI_COUNT])

        created = 0
        for i in range(existing_count, TOTAL_STUDENTS):
            given = random.choice(FIRST_NAMES)
            family = random.choice(LAST_NAMES)
            email = _clean_email(given, family, i)
            ref = f"{REF_PREFIX}-{i:04d}"
            if (await s.execute(select(Student).where(Student.student_ref == ref))).scalars().first():
                continue

            is_alumnus = i in alumni_indices
            code = "ICR-PHD" if random.random() < 0.7 else "ICR-MDRES"
            prog = progs[code]
            limit_days = 1460 if code == "ICR-PHD" else 1095

            if is_alumnus:
                # Fully in the past: started 5-6 years ago, finished on schedule.
                months_ago = random.randint(limit_days // 30 + 6, limit_days // 30 + 14)
                status = StudentStatus.completed
            else:
                months_ago = random.randint(1, limit_days // 30 + 2)
                roll = random.random()
                if roll < 0.05:
                    status = StudentStatus.withdrawn
                elif roll < 0.12:
                    status = StudentStatus.suspended
                elif roll < 0.18:
                    status = StudentStatus.on_leave
                elif months_ago <= 1:
                    status = StudentStatus.registered
                else:
                    status = StudentStatus.active

            start = TODAY - timedelta(days=months_ago * 30)
            expected_end = start + timedelta(days=limit_days)

            person = await get_or_create_person(s, given, family, email)
            s.add(PersonRelationship(
                person_id=person.id, relationship_type=PersonRelationshipType.student,
                valid_from=start, valid_to=None,
            ))
            await s.flush()

            student = Student(
                person_id=person.id, student_ref=ref, programme_id=prog.id,
                department_id=dept.id if dept else None,
                start_date=start, expected_end_date=expected_end,
                original_expected_end_date=expected_end,
                study_mode=StudyMode.full_time if random.random() < 0.85 else StudyMode.part_time,
                status=status,
            )
            s.add(student)
            await s.flush()

            topic = random.choice(TOPICS)
            s.add(ResearchProject(student_id=student.id, research_topic=topic, start_date=start))

            pi = pis[i % len(pis)]
            co = cos[i % len(cos)]
            s.add(SupervisorRelationship(
                student_id=student.id, supervisor_person_id=pi.id,
                role=SupervisorRole.primary, status=SupervisionStatus.active,
                valid_from=start, valid_to=None,
            ))
            s.add(SupervisorRelationship(
                student_id=student.id, supervisor_person_id=co.id,
                role=SupervisorRole.co_supervisor, status=SupervisionStatus.active,
                valid_from=start, valid_to=None,
            ))

            for defn in defs_by_prog[code]:
                due = start + timedelta(days=defn.due_offset_days)
                if is_alumnus or due <= TODAY - timedelta(days=60):
                    m_status = MilestoneStatus.decided
                elif due <= TODAY:
                    m_status = MilestoneStatus.due
                elif due > TODAY + timedelta(days=400):
                    continue  # far future - the generator will create it in time
                else:
                    m_status = MilestoneStatus.not_started
                s.add(Milestone(student_id=student.id, milestone_definition_id=defn.id,
                                 due_date=due, status=m_status))

            funder = funder_list[i % len(funder_list)]
            funding_status = FundingStatus.active
            if status in (StudentStatus.withdrawn, StudentStatus.completed):
                funding_status = FundingStatus.ended
            s.add(FundingArrangement(
                student_id=student.id,
                funding_type=FundingType.research_council if "Council" in funder.name
                else FundingType.external,
                funding_source_id=funder.id,
                stipend_amount=Decimal(random.choice([19500, 20000, 21000, 21500, 22000])),
                currency="GBP",
                valid_from=start,
                valid_to=expected_end if funding_status == FundingStatus.ended else None,
                status=funding_status,
                funder_reference=f"{code}-{ref}",
            ))

            # Every student gets at least one real, openable document.
            s.add(_placeholder_document(
                owner_type="student", owner_id=student.id, doc_type="progress_report",
                filename=f"{ref}-progress-report.txt",
                body_text=(
                    f"Progress report for {given} {family} ({ref})\n"
                    f"Programme: {prog.name}\nTopic: {topic}\n"
                    f"Status as of {TODAY.isoformat()}: {status.value}\n"
                ),
            ))

            if is_alumnus:
                grad_date = expected_end
                thesis_title = f"{topic} — a thesis submitted for the degree of {code.split('-')[1]}"
                thesis = Thesis(
                    student_id=student.id, title=thesis_title,
                    status=ThesisStatus.approved,
                    intention_to_submit_at=datetime.combine(
                        expected_end - timedelta(days=120), datetime.min.time(), tzinfo=timezone.utc),
                    submitted_at=datetime.combine(
                        expected_end - timedelta(days=30), datetime.min.time(), tzinfo=timezone.utc),
                )
                s.add(thesis)
                s.add(Completion(
                    student_id=student.id, status=CompletionStatus.graduated,
                    requirements_met_at=datetime.combine(
                        expected_end - timedelta(days=14), datetime.min.time(), tzinfo=timezone.utc),
                    award_confirmed_at=datetime.combine(
                        expected_end - timedelta(days=7), datetime.min.time(), tzinfo=timezone.utc),
                    graduation_date=grad_date,
                ))
                s.add(Award(
                    student_id=student.id,
                    title=f"Doctor of Philosophy" if code == "ICR-PHD" else "Doctor of Medicine (Research)",
                    award_type="PhD" if code == "ICR-PHD" else "MD(Res)",
                    conferred_at=datetime.combine(grad_date, datetime.min.time(), tzinfo=timezone.utc),
                    classification="PhD" if code == "ICR-PHD" else "MD(Res)",
                    classification_state="published",
                    published_at=datetime.combine(grad_date, datetime.min.time(), tzinfo=timezone.utc),
                ))
                s.add(PersonRelationship(
                    person_id=person.id, relationship_type=PersonRelationshipType.alumni,
                    valid_from=grad_date, valid_to=None,
                ))
                s.add(_placeholder_document(
                    owner_type="student", owner_id=student.id, doc_type="thesis",
                    filename=f"{ref}-thesis.txt",
                    body_text=f"{thesis_title}\n\nSubmitted by {given} {family}\nAwarded: {grad_date.isoformat()}\n",
                ))
                s.add(_placeholder_document(
                    owner_type="student", owner_id=student.id, doc_type="certificate",
                    filename=f"{ref}-certificate.txt",
                    body_text=(
                        f"This certifies that {given} {family} has been awarded the degree of "
                        f"{'Doctor of Philosophy' if code == 'ICR-PHD' else 'Doctor of Medicine (Research)'} "
                        f"on {grad_date.isoformat()}.\n"
                    ),
                ))

            created += 1
            if created % 25 == 0:
                await s.flush()
                print(f"  ... {created} students created")

        await s.commit()
        print(f"Bulk student seed complete: {created} created "
              f"(target {TOTAL_STUDENTS}, {ALUMNI_COUNT} reached alumni).")


if __name__ == "__main__":
    asyncio.run(main())
