"""Bulk ICR student population — 300 students spread across the real pipeline stages.

Extends the small hand-curated cohort from `seed_icr_cohort.py` (14 students) into a
realistic-scale population for load-testing the UI, Weekly Review Queue, Pattern Lab,
and the AI intelligence layer against something bigger than a handful of rows.

Every field is generated to look exactly like a real record the system itself would
have produced — not an obviously-synthetic test fixture:
  - `student_ref` uses the SAME format the real registration flow generates
    (`PGR-{registration year}-{6 uppercase hex}`, see
    `app/modules/student_record/service.py::_generate_student_ref`), computed from
    each student's own start date so a 2022 registrant gets a 2022-dated ref, exactly
    as if they had actually registered that year.
  - Documents are real, valid PDFs (via reportlab, the same library the platform's
    own certificate generator uses) written through the real object store — opening
    one in an actual PDF viewer works, it is not a renamed .txt file.

Distribution (out of 300):
  - 5 fully completed through to Alumni (thesis approved, completion graduated,
    award published, PersonRelationship flipped to alumni) — with a thesis PDF and
    a certificate PDF attached.
  - ~20 on_leave / suspended (realistic exceptions)
  - ~10 withdrawn
  - the rest active/registered, spread across the pipeline from month 1 to month 50
    so milestones land at every stage (not started / due / decided).

Requires `scripts/seed_icr.py` to have already run (ICR-PHD / ICR-MDRES programmes
and funders). Idempotent: tagged internally via `ResearchProject.research_group =
"ICR Demo Cohort"` (a real, legitimate-looking field — not a fake ref prefix) rather
than anything visible as obviously-seeded data; safe to re-run.

    python -m scripts.seed_icr            (if not already run)
    python -m scripts.seed_bulk_students
"""
from __future__ import annotations

import asyncio
import io
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
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
TODAY = date.today()

# Internal idempotency tag — a plausible real value (a lab/cohort label), never a
# fake-looking ref prefix. Nothing in the UI treats this as special.
SEED_TAG = "ICR Demo Cohort"

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


def _generate_student_ref(year: int) -> str:
    """Exactly mirrors app/modules/student_record/service.py::_generate_student_ref,
    parameterised by year so a historical registrant gets a ref dated to the year
    they actually registered, not today's year."""
    return f"PGR-{year}-{uuid.uuid4().hex[:6].upper()}"


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


def _pdf_bytes(title: str, lines: list[str]) -> bytes:
    """A real, valid single-page PDF — opens correctly in any PDF viewer."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 15)
    c.drawString(2 * cm, height - 3 * cm, title)
    c.setFont("Helvetica", 11)
    y = height - 4.2 * cm
    for line in lines:
        c.drawString(2 * cm, y, line[:110])
        y -= 0.7 * cm
    c.showPage()
    c.save()
    return buf.getvalue()


def _save_document(store, owner_type: str, owner_id, doc_type: str, filename: str,
                    pdf_bytes: bytes, uploaded_by=None) -> Document:
    key, checksum, size = store.save(pdf_bytes, suffix=".pdf")
    return Document(
        owner_type=owner_type, owner_id=owner_id, doc_type=doc_type,
        filename=filename, content_type="application/pdf", size_bytes=size,
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
            select(func.count()).select_from(ResearchProject)
            .where(ResearchProject.research_group == SEED_TAG)
        )).scalar_one()
        if existing_count >= TOTAL_STUDENTS:
            print(f"  = {existing_count} students already seeded under '{SEED_TAG}' - skipped")
            return

        pis = [await get_or_create_person(s, g, f, _clean_email(g, f, i))
               for i, (g, f) in enumerate(PI_NAMES)]
        cos = [await get_or_create_person(s, g, f, _clean_email(g, f, 100 + i))
               for i, (g, f) in enumerate(CO_SUP_NAMES)]
        await s.flush()

        store = get_object_store()

        # Deterministic assignment of which sequence numbers become the 5 alumni,
        # spread evenly rather than clustered at the front.
        alumni_indices = set(list(range(0, TOTAL_STUDENTS, TOTAL_STUDENTS // ALUMNI_COUNT))[:ALUMNI_COUNT])

        created = 0
        for i in range(existing_count, TOTAL_STUDENTS):
            given = random.choice(FIRST_NAMES)
            family = random.choice(LAST_NAMES)
            email = _clean_email(given, family, i)

            is_alumnus = i in alumni_indices
            code = "ICR-PHD" if random.random() < 0.7 else "ICR-MDRES"
            prog = progs[code]
            limit_days = 1460 if code == "ICR-PHD" else 1095

            if is_alumnus:
                # Fully in the past: started several years ago, finished on schedule.
                months_ago = random.randint(limit_days // 30 + 6, limit_days // 30 + 14)
                status = StudentStatus.completed
            else:
                months_ago = random.randint(1, limit_days // 30 + 2)
                roll = random.random()
                if roll < 0.03:
                    status = StudentStatus.withdrawn
                elif roll < 0.09:
                    status = StudentStatus.suspended
                elif roll < 0.16:
                    status = StudentStatus.on_leave
                elif months_ago <= 1:
                    status = StudentStatus.registered
                else:
                    status = StudentStatus.active

            start = TODAY - timedelta(days=months_ago * 30)
            expected_end = start + timedelta(days=limit_days)
            ref = _generate_student_ref(start.year)
            while (await s.execute(select(Student).where(Student.student_ref == ref))).scalars().first():
                ref = _generate_student_ref(start.year)  # astronomically unlikely, but stay correct

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
            s.add(ResearchProject(student_id=student.id, research_topic=topic,
                                   start_date=start, research_group=SEED_TAG))

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

            # Every student gets at least one real, openable PDF document.
            s.add(_save_document(
                store, owner_type="student", owner_id=student.id, doc_type="progress_report",
                filename=f"{ref}-progress-report.pdf",
                pdf_bytes=_pdf_bytes(
                    f"Progress Report - {given} {family} ({ref})",
                    [
                        f"Programme: {prog.name}",
                        f"Research topic: {topic}",
                        f"Status as of {TODAY.isoformat()}: {status.value.replace('_', ' ')}",
                        f"Primary supervisor: {pi.given_name} {pi.family_name}",
                        f"Co-supervisor: {co.given_name} {co.family_name}",
                    ],
                ),
            ))

            if is_alumnus:
                grad_date = expected_end
                degree = "Doctor of Philosophy" if code == "ICR-PHD" else "Doctor of Medicine (Research)"
                thesis_title = f"{topic} - a thesis submitted for the degree of {degree}"
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
                    student_id=student.id, title=degree,
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
                s.add(_save_document(
                    store, owner_type="student", owner_id=student.id, doc_type="thesis",
                    filename=f"{ref}-thesis.pdf",
                    pdf_bytes=_pdf_bytes(thesis_title, [
                        f"Submitted by {given} {family}",
                        f"Student reference: {ref}",
                        f"Submitted: {(expected_end - timedelta(days=30)).isoformat()}",
                        f"Approved: {grad_date.isoformat()}",
                    ]),
                ))
                s.add(_save_document(
                    store, owner_type="student", owner_id=student.id, doc_type="certificate",
                    filename=f"{ref}-certificate.pdf",
                    pdf_bytes=_pdf_bytes("Certificate of Award", [
                        f"This certifies that {given} {family} ({ref})",
                        f"has been awarded the degree of {degree}",
                        f"on {grad_date.isoformat()}.",
                        "Institute of Cancer Research",
                    ]),
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
