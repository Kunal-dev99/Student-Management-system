"""ICR module — seed a demonstration cohort on the ICR pathways.

Additive and idempotent: creates persons/students only under the ICR-* student_ref
prefix, on the programmes created by scripts/seed_icr.py. Existing data is never
touched. Re-running skips students that already exist.

Milestone states are staged deliberately so the ICR modules have something true to
show: students before, at, over and past the Transfer Viva, plus students at the
30-month data barrier and approaching the 48-month hard limit.

    python -m scripts.seed_icr (first)  then  python -m scripts.seed_icr_cohort
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionFactory
# Register every mapper before use — cross-module foreign keys (funding to
# research_award, project to research_opportunity) only resolve once all model
# modules are imported, exactly as the Alembic env does.
from app.db import registry as _registry  # noqa: F401
from app.modules.funding.constants import FundingStatus, FundingType
from app.modules.funding.models import FundingArrangement, FundingSource
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.models import Person, PersonRelationship
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone, MilestoneDefinition
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Department, Programme, ResearchProject, Student
from app.modules.supervision.constants import SupervisionStatus, SupervisorRole
from app.modules.supervision.models import SupervisorRelationship

TODAY = date.today()

# (ref suffix, given, family, programme code, months since start, topic, funder, stipend)
COHORT = [
    # --- Non-clinical PhD: staged across the 4-year model -------------------
    ("0001", "Aisha", "Okonjo", "ICR-PHD", 3, "Targeting BRCA2 synthetic lethality", "Cancer Research UK (CRUK)", 21500),
    ("0002", "Ravi", "Chandra", "ICR-PHD", 7, "Single-cell atlas of prostate tumour microenvironment", "Cancer Research UK (CRUK)", 21500),
    ("0003", "Marta", "Kowalski", "ICR-PHD", 11, "Radiotherapy response biomarkers in glioma", "Medical Research Council (MRC)", 21000),
    ("0004", "Tomas", "Lindgren", "ICR-PHD", 13, "Epigenetic drivers of paediatric sarcoma", "Cancer Research UK (CRUK)", 21500),
    ("0005", "Nadia", "Haddad", "ICR-PHD", 15, "Drug-tolerant persister cells in melanoma", "Breast Cancer Now", 21200),
    ("0006", "Peter", "Osei", "ICR-PHD", 20, "Computational modelling of clonal evolution", "Medical Research Council (MRC)", 21000),
    ("0007", "Lucy", "Fairbairn", "ICR-PHD", 26, "PARP inhibitor resistance mechanisms", "Cancer Research UK (CRUK)", 21500),
    ("0008", "Hiroshi", "Tanabe", "ICR-PHD", 31, "Mass-spectrometry proteomics of tumour exosomes", "ICR Corporate Partnership Pool", 22000),
    ("0009", "Elena", "Rossi", "ICR-PHD", 40, "Immune evasion in triple-negative breast cancer", "Breast Cancer Now", 21200),
    ("0010", "Samuel", "Adeyemi", "ICR-PHD", 45, "CRISPR screens for radiosensitisers", "Cancer Research UK (CRUK)", 21500),
    # --- Clinical MD(Res): condensed model ---------------------------------
    ("0011", "Priya", "Raghavan", "ICR-MDRES", 6, "Translational trial of neoadjuvant immunotherapy", "Medical Research Council (MRC)", 21000),
    ("0012", "James", "Whitlock", "ICR-MDRES", 14, "Circulating tumour DNA in surgical oncology", "Cancer Research UK (CRUK)", 21500),
    ("0013", "Amara", "Diallo", "ICR-MDRES", 25, "Precision radiotherapy planning in head and neck cancer", "ICR Corporate Partnership Pool", 22000),
    ("0014", "Grace", "Mbeki", "ICR-MDRES", 33, "Biomarker-guided endocrine therapy", "Breast Cancer Now", 21200),
]

# Supervisors to create for the ICR labs (Principal Investigators).
PIS = [
    ("Helena", "Vaughan-Price", "h.vaughanprice@icr.example.ac.uk"),
    ("Idris", "Mahmood", "i.mahmood@icr.example.ac.uk"),
    ("Claire", "Beaumont", "c.beaumont@icr.example.ac.uk"),
]
CO_SUPS = [
    ("Yusuf", "Karim", "y.karim@icr.example.ac.uk"),          # computational genomics
    ("Sinead", "O'Rourke", "s.orourke@icr.example.ac.uk"),    # wet-lab biology
]


async def get_or_create_person(s, given, family, email) -> Person:
    p = (await s.execute(select(Person).where(Person.email == email))).scalars().first()
    if p is None:
        p = Person(given_name=given, family_name=family, email=email)
        s.add(p)
        await s.flush()
    return p


async def main() -> None:
    async with SessionFactory() as s:
        progs = {p.code: p for p in (await s.execute(
            select(Programme).where(Programme.code.in_(["ICR-PHD", "ICR-MDRES"]))
        )).scalars().all()}
        if not progs:
            raise SystemExit("Run `python -m scripts.seed_icr` first — ICR programmes are missing.")

        dept = (await s.execute(select(Department).where(Department.code == "ICR"))).scalars().first()
        funders = {f.name: f for f in (await s.execute(select(FundingSource))).scalars().all()}
        defs_by_prog: dict = {}
        for code, prog in progs.items():
            defs_by_prog[code] = (await s.execute(
                select(MilestoneDefinition)
                .where(MilestoneDefinition.programme_id == prog.id)
                .order_by(MilestoneDefinition.due_offset_days)
            )).scalars().all()

        pis = [await get_or_create_person(s, g, f, e) for g, f, e in PIS]
        cos = [await get_or_create_person(s, g, f, e) for g, f, e in CO_SUPS]

        created = 0
        for i, (suffix, given, family, code, months, topic, funder_name, stipend) in enumerate(COHORT):
            ref = f"ICR-{suffix}"
            if (await s.execute(select(Student).where(Student.student_ref == ref))).scalars().first():
                continue

            prog = progs[code]
            start = TODAY - timedelta(days=months * 30)
            limit_days = 1460 if code == "ICR-PHD" else 1095
            expected_end = start + timedelta(days=limit_days)

            person = await get_or_create_person(
                s, given, family, f"{given.lower()}.{family.lower().replace(chr(39), '')}@icr.example.ac.uk")
            # Insert the identity row directly: assigning to person.relationships would
            # lazy-load the collection and trip MissingGreenlet on the async session.
            s.add(PersonRelationship(
                person_id=person.id, relationship_type=PersonRelationshipType.student,
                valid_from=start, valid_to=None))
            await s.flush()

            student = Student(
                person_id=person.id, student_ref=ref, programme_id=prog.id,
                department_id=dept.id if dept else None,
                start_date=start, expected_end_date=expected_end,
                original_expected_end_date=expected_end,
                study_mode=StudyMode.full_time,
                status=StudentStatus.active,
            )
            s.add(student)
            await s.flush()

            s.add(ResearchProject(student_id=student.id, research_topic=topic, start_date=start))

            # Supervisory ecosystem: PI + complementary co-supervisor.
            s.add(SupervisorRelationship(
                student_id=student.id, supervisor_person_id=pis[i % len(pis)].id,
                role=SupervisorRole.primary, status=SupervisionStatus.active,
                valid_from=start, valid_to=None))
            s.add(SupervisorRelationship(
                student_id=student.id, supervisor_person_id=cos[i % len(cos)].id,
                role=SupervisorRole.co_supervisor, status=SupervisionStatus.active,
                valid_from=start, valid_to=None))

            # Milestones: instantiate every definition whose due date has arrived,
            # marking the earlier ones decided so the pipeline looks lived-in.
            for defn in defs_by_prog[code]:
                due = start + timedelta(days=defn.due_offset_days)
                if due > TODAY + timedelta(days=400):
                    continue  # far future — the generator will create it in time
                if due <= TODAY - timedelta(days=60):
                    status = MilestoneStatus.decided
                elif due <= TODAY:
                    status = MilestoneStatus.due
                else:
                    status = MilestoneStatus.not_started
                s.add(Milestone(student_id=student.id, milestone_definition_id=defn.id,
                                due_date=due, status=status))

            # Stipend, tied to an ICR funder pillar.
            src = funders.get(funder_name)
            s.add(FundingArrangement(
                student_id=student.id,
                funding_type=FundingType.research_council if "Research Council" in funder_name
                else FundingType.external,
                funding_source_id=src.id if src else None,
                stipend_amount=Decimal(stipend), currency="GBP",
                valid_from=start, valid_to=None,
                status=FundingStatus.active,
                funder_reference=f"{code}-{suffix}",
            ))
            created += 1
            print(f"  + {ref} {given} {family} — {code}, {months} months in")

        await s.commit()
        print(f"ICR cohort seed complete ({created} created, {len(COHORT) - created} already present).")


if __name__ == "__main__":
    asyncio.run(main())
