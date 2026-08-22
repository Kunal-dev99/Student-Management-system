"""Generate a representative PGR cohort for UAT and measurement (Phase 7, item R1).

Produces realistic volumes across the whole lifecycle — students at every stage, funding over time,
supervision histories, milestones, theses, suspensions — and **deliberately plants known data
problems** so the funding-integrity and supervision-compliance engines have something real to find.

The generator prints exactly what it planted. That is the point: it turns "the integrity report
shows some warnings" into "the report found 7 of the 7 problems we planted, and nothing else."

Deterministic: the same `--seed` always produces the same cohort, so results are comparable
between runs and between environments.

    PYTHONPATH=. python scripts/generate_cohort.py --students 60 --seed 42
    PYTHONPATH=. python scripts/generate_cohort.py --students 200 --seed 7 --prefix UAT
"""
from __future__ import annotations

import argparse
import asyncio
import random
import uuid
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionFactory

# Import every model module so SQLAlchemy can resolve cross-module foreign keys
# (e.g. research_demand.raised_by_user_id → users.id).
import app.modules.identity.models  # noqa: F401
import app.modules.workflow.models  # noqa: F401
import app.modules.admissions.models  # noqa: F401
import app.modules.completion.models  # noqa: F401
import app.modules.documents.models  # noqa: F401
import app.modules.exports.models  # noqa: F401
import app.modules.integration.models  # noqa: F401
import app.modules.notifications.models  # noqa: F401
import app.modules.audit.models  # noqa: F401
from app.modules.funding.constants import FundingStatus, FundingType, PaymentFrequency
from app.modules.funding.models import FundingArrangement, FundingSource
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.models import Person, PersonRelationship
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone, MilestoneDefinition
from app.modules.research.constants import AwardStatus, DemandStatus
from app.modules.research.models import ResearchAward, ResearchDemand
from app.modules.recruitment.constants import ApplicationRoute, CandidateStage, OpportunityStatus
from app.modules.recruitment.models import Application, ResearchOpportunity
from app.modules.student_record.constants import (
    LifecycleEventStatus,
    LifecycleEventType,
    StudentStatus,
    StudyMode,
)
from app.modules.student_record.models import (
    Department,
    Programme,
    ResearchArea,
    ResearchProject,
    Student,
    StudentLifecycleEvent,
)
from app.modules.supervision.constants import SupervisionStatus, SupervisorRole
from app.modules.supervision.models import SupervisionMeeting, SupervisorRelationship
from app.modules.thesis.constants import ThesisStatus
from app.modules.thesis.models import Thesis

GIVEN = ["Amara", "Ben", "Chen", "Dara", "Elif", "Farid", "Gita", "Hugo", "Iris", "Jonas",
         "Kaia", "Liam", "Mira", "Noor", "Omar", "Priya", "Quinn", "Rosa", "Sami", "Tara",
         "Uma", "Viktor", "Wren", "Xiu", "Yusuf", "Zara"]
FAMILY = ["Abara", "Bennett", "Costa", "Duarte", "Eriksen", "Fontaine", "Grigsby", "Hartley",
          "Ibrahim", "Jensen", "Kowalski", "Lindqvist", "Moreau", "Nakamura", "Okafor",
          "Petrov", "Quirke", "Rahman", "Silva", "Tanaka", "Ueda", "Varga", "Whitlock", "Zhao"]
NATIONALITIES = ["British", "Irish", "Indian", "Nigerian", "Chinese", "Brazilian", "German",
                 "Spanish", "Kenyan", "Canadian", None]   # None exercises statutory validation
AREAS = ["Machine Learning", "Robotics", "Health Informatics", "Climate Systems",
         "Materials Science", "Computational Biology"]

# Deliberate problems, as a share of the cohort. Each one is counted and reported.
P_FUNDING_GAP = 0.10          # months with no funding mid-journey
P_FUNDING_SHORT = 0.12        # funding ends before the expected end date
P_NO_MEETINGS = 0.15          # never had a supervision meeting
P_STALE_MEETINGS = 0.15       # last meeting well over the 90-day expectation
P_MILESTONE_OVERDUE = 0.12    # an undecided milestone past its due date
P_UNLINKED_FUNDING = 0.10     # finance references but no research award
P_SUSPENDED = 0.08            # currently suspended


async def purge(prefix: str) -> int:
    """Remove a previously generated cohort so repeated UAT runs stay comparable.

    Without this, each run stacks on the last and the integrity report mixes cohorts — which
    makes 'planted vs detected' meaningless.
    """
    from sqlalchemy import delete

    async with SessionFactory() as s:
        students = list((await s.execute(
            select(Student).where(Student.student_ref.like(f"{prefix}-%"))
        )).scalars().all())
        if not students:
            return 0
        person_ids = [st.person_id for st in students]
        # Applications reference the person, not the student, so clear them explicitly.
        await s.execute(delete(Application).where(Application.person_id.in_(person_ids)))
        for st in students:
            await s.delete(st)          # student children cascade
        await s.flush()
        await s.execute(delete(PersonRelationship).where(PersonRelationship.person_id.in_(person_ids)))
        await s.execute(delete(Person).where(Person.id.in_(person_ids)))
        await s.commit()
        return len(students)


async def main(n_students: int, seed: int, prefix: str, clean: bool) -> None:
    rng = random.Random(seed)
    planted: Counter = Counter()
    today = date.today()

    if clean:
        removed = await purge(prefix)
        print(f"Removed {removed} previously generated student(s) with prefix {prefix}.")

    async with SessionFactory() as s:
        # --- reference data -------------------------------------------------------------
        dept = (await s.execute(select(Department).limit(1))).scalar_one_or_none()
        if dept is None:
            dept = Department(name="Engineering & Computing", code="ENGCMP")
            s.add(dept)
            await s.flush()

        areas = {a.name: a for a in (await s.execute(select(ResearchArea))).scalars().all()}
        for name in AREAS:
            if name not in areas:
                area = ResearchArea(name=name, code=name[:12].upper().replace(" ", "-"),
                                    department_id=dept.id)
                s.add(area)
                await s.flush()
                areas[name] = area

        programmes = list((await s.execute(select(Programme))).scalars().all())
        if not programmes:
            for pname, pcode in (("PhD Computer Science", "PHD-CS"), ("PhD Engineering", "PHD-ENG")):
                p = Programme(name=pname, code=pcode, department_id=dept.id)
                s.add(p)
                programmes.append(p)
            await s.flush()

        # Every programme needs milestone definitions for progression to be meaningful.
        for prog in programmes:
            existing = (await s.execute(
                select(MilestoneDefinition).where(MilestoneDefinition.programme_id == prog.id)
            )).scalars().first()
            if existing is None:
                for mname, offset in (("Induction Review", 30), ("Confirmation Review", 270),
                                      ("Annual Review", 540)):
                    s.add(MilestoneDefinition(programme_id=prog.id, name=mname,
                                              due_offset_days=offset))
        await s.flush()

        funders = list((await s.execute(select(FundingSource))).scalars().all())
        if not funders:
            for fname, ftype in (("UKRI EPSRC", "research_council"), ("Wellcome Trust", "charity"),
                                 ("University Scholarship Fund", "institutional")):
                f = FundingSource(name=fname, funder_type=ftype)
                s.add(f)
                funders.append(f)
            await s.flush()

        # --- research context: awards → demand → positions -------------------------------
        awards = []
        for i in range(max(2, n_students // 15)):
            ref = f"{prefix}-AWD-{seed}-{i + 1:03d}"
            if (await s.execute(select(ResearchAward).where(ResearchAward.award_ref == ref))).scalar_one_or_none():
                continue
            aw = ResearchAward(
                award_ref=ref, title=f"{rng.choice(AREAS)} Programme Grant",
                funder_id=rng.choice(funders).id,
                # Awards must predate the students they fund, or every arrangement trips
                # `funding_precedes_award` and drowns the signal we actually care about.
                # Students start at most 1500 days ago (below), so awards start before that.
                start_date=today - timedelta(days=rng.randint(1600, 2600)),
                end_date=today + timedelta(days=rng.randint(400, 1800)),
                value=Decimal(rng.randrange(300_000, 4_000_000, 50_000)), currency="GBP",
                status=AwardStatus.active,
                # Half arrive from the Research system, so read-only behaviour is exercised.
                source_system="research" if i % 2 == 0 else None,
                external_ref=f"RS-{seed}-{i}" if i % 2 == 0 else None,
            )
            s.add(aw)
            awards.append(aw)
        await s.flush()

        positions = []
        for i, aw in enumerate(awards):
            demand = ResearchDemand(
                title=f"PGR researcher for {aw.title}", research_award_id=aw.id,
                research_area_id=areas[rng.choice(AREAS)].id, department_id=dept.id,
                requested_places=rng.randint(1, 3),
                justification="Generated for UAT.", target_start_date=today + timedelta(days=90),
                status=DemandStatus.positioned,
            )
            s.add(demand)
            await s.flush()
            opp = ResearchOpportunity(
                title=f"PhD in {rng.choice(AREAS)}", department_id=dept.id,
                research_area_id=demand.research_area_id,
                positions_available=demand.requested_places, positions_filled=0,
                expected_duration_months=rng.choice([36, 42, 48]),
                status=OpportunityStatus.open,
                research_demand_id=demand.id, research_award_id=aw.id,
                stipend_amount=Decimal(rng.randrange(17_000, 21_000, 500)), currency="GBP",
            )
            s.add(opp)
            positions.append(opp)
        await s.flush()

        # --- supervisors ------------------------------------------------------------------
        # Supervisors are reused across runs (they are staff, not cohort members), so this is a
        # get-or-create rather than an insert — otherwise a re-run collides on the email.
        supervisors = []
        for i in range(max(3, n_students // 6)):
            email = f"sup{seed}{i}@uni.example.ac.uk"
            existing = (await s.execute(select(Person).where(Person.email == email))).scalar_one_or_none()
            if existing is not None:
                supervisors.append(existing)
                continue
            p = Person(given_name=rng.choice(GIVEN), family_name=rng.choice(FAMILY),
                       email=email, nationality="British")
            p.relationships = [PersonRelationship(
                relationship_type=PersonRelationshipType.employee,
                valid_from=today - timedelta(days=rng.randint(400, 3000)), valid_to=None,
                source_system="hr")]
            s.add(p)
            supervisors.append(p)
        await s.flush()

        # --- students ---------------------------------------------------------------------
        statuses = ([StudentStatus.active] * 6 + [StudentStatus.registered] * 2
                    + [StudentStatus.completed, StudentStatus.withdrawn])
        for i in range(n_students):
            prog = rng.choice(programmes)
            opp = rng.choice(positions) if positions and rng.random() < 0.7 else None
            start = today - timedelta(days=rng.randint(30, 1500))
            months = opp.expected_duration_months if opp else 42
            expected_end = start + timedelta(days=int(months * 30.44))
            status = rng.choice(statuses)

            person = Person(
                given_name=rng.choice(GIVEN), family_name=rng.choice(FAMILY),
                email=f"{prefix.lower()}{seed}s{i}@student.example.ac.uk",
                nationality=rng.choice(NATIONALITIES),
                date_of_birth=date(rng.randint(1985, 2003), rng.randint(1, 12), rng.randint(1, 28)),
            )
            person.relationships = [PersonRelationship(
                relationship_type=PersonRelationshipType.student,
                valid_from=start, valid_to=None)]
            s.add(person)
            await s.flush()

            student = Student(
                person_id=person.id, student_ref=f"{prefix}-{seed}-{i + 1:04d}",
                programme_id=prog.id, department_id=dept.id,
                research_area_id=opp.research_area_id if opp else areas[rng.choice(AREAS)].id,
                start_date=start, expected_end_date=expected_end,
                original_expected_end_date=expected_end,
                study_mode=StudyMode.part_time if rng.random() < 0.15 else StudyMode.full_time,
                status=status,
            )
            s.add(student)
            await s.flush()

            # Application, so the entry route is populated for reporting.
            s.add(Application(
                person_id=person.id,
                route=ApplicationRoute.opportunity_led if opp else ApplicationRoute.student_led,
                research_opportunity_id=opp.id if opp else None,
                research_area_id=student.research_area_id,
                proposal_document_ref=None if opp else f"proposal-{i}.pdf",
                current_stage=CandidateStage.converted,
            ))
            if opp:
                opp.positions_filled += 1

            # Research project — the hinge of the funding lineage.
            unlinked = rng.random() < P_UNLINKED_FUNDING
            s.add(ResearchProject(
                student_id=student.id,
                research_topic=f"{rng.choice(AREAS)}: {rng.choice(['modelling','analysis','synthesis','evaluation'])} study",
                research_area_id=student.research_area_id,
                research_award_id=None if unlinked else (opp.research_award_id if opp else None),
                research_opportunity_id=opp.id if opp else None,
                start_date=start,
            ))

            # --- funding ---------------------------------------------------------------
            award_id = None if unlinked else (opp.research_award_id if opp else None)
            gap = rng.random() < P_FUNDING_GAP
            short = rng.random() < P_FUNDING_SHORT
            if gap:
                planted["funding_gap"] += 1
                mid = start + timedelta(days=400)
                s.add(FundingArrangement(
                    student_id=student.id, funding_type=FundingType.research_council,
                    funding_source_id=rng.choice(funders).id, research_award_id=award_id,
                    stipend_amount=Decimal("18000"), currency="GBP",
                    valid_from=start, valid_to=mid, status=FundingStatus.ended,
                    payment_frequency=PaymentFrequency.monthly,
                ))
                s.add(FundingArrangement(
                    student_id=student.id, funding_type=FundingType.research_council,
                    funding_source_id=rng.choice(funders).id, research_award_id=award_id,
                    stipend_amount=Decimal("18500"), currency="GBP",
                    valid_from=mid + timedelta(days=rng.randint(60, 150)),   # the hole
                    valid_to=expected_end, status=FundingStatus.active,
                ))
            else:
                end = (expected_end - timedelta(days=rng.randint(200, 400))) if short else expected_end
                if short:
                    planted["funding_ends_before_expected_end"] += 1
                arr = FundingArrangement(
                    student_id=student.id,
                    funding_type=rng.choice(list(FundingType)),
                    funding_source_id=rng.choice(funders).id, research_award_id=award_id,
                    stipend_amount=Decimal(rng.randrange(16_000, 21_000, 250)), currency="GBP",
                    valid_from=start, valid_to=end, status=FundingStatus.active,
                    payment_frequency=PaymentFrequency.monthly,
                    cost_centre=f"CC-{rng.randint(1000, 9999)}",
                    project_code=f"PRJ-{rng.randint(100, 999)}" if unlinked else None,
                )
                s.add(arr)
            if unlinked:
                planted["arrangement_award_unlinked"] += 1

            # --- supervision -------------------------------------------------------------
            primary = rng.choice(supervisors)
            s.add(SupervisorRelationship(
                student_id=student.id, supervisor_person_id=primary.id,
                role=SupervisorRole.primary, status=SupervisionStatus.active,
                valid_from=start, valid_to=None,
            ))
            if rng.random() < 0.5:
                co = rng.choice([x for x in supervisors if x.id != primary.id])
                s.add(SupervisorRelationship(
                    student_id=student.id, supervisor_person_id=co.id,
                    role=SupervisorRole.co_supervisor, status=SupervisionStatus.active,
                    valid_from=start, valid_to=None, weighting_pct=30,
                ))

            roll = rng.random()
            if roll < P_NO_MEETINGS:
                planted["no_supervision_meeting"] += 1          # none recorded at all
            elif roll < P_NO_MEETINGS + P_STALE_MEETINGS:
                planted["stale_supervision_meeting"] += 1
                s.add(SupervisionMeeting(
                    student_id=student.id, supervisor_person_id=primary.id,
                    met_on=today - timedelta(days=rng.randint(120, 400)),
                    notes="Generated for UAT.", actions="Continue as planned.",
                ))
            else:
                for back in (20, 110, 200):
                    if start <= today - timedelta(days=back):
                        s.add(SupervisionMeeting(
                            student_id=student.id, supervisor_person_id=primary.id,
                            met_on=today - timedelta(days=back),
                            notes="Generated for UAT.", actions="Continue as planned.",
                        ))

            # --- progression ---------------------------------------------------------------
            defs = list((await s.execute(
                select(MilestoneDefinition).where(MilestoneDefinition.programme_id == prog.id)
                .order_by(MilestoneDefinition.due_offset_days)
            )).scalars().all())
            overdue = rng.random() < P_MILESTONE_OVERDUE
            for j, d in enumerate(defs):
                due = start + timedelta(days=d.due_offset_days)
                if due > today + timedelta(days=365):
                    continue
                if overdue and j == len(defs) - 1:
                    s.add(Milestone(student_id=student.id, milestone_definition_id=d.id,
                                    due_date=today - timedelta(days=rng.randint(20, 200)),
                                    status=MilestoneStatus.due))
                    planted["milestone_overdue"] += 1
                else:
                    s.add(Milestone(
                        student_id=student.id, milestone_definition_id=d.id, due_date=due,
                        status=MilestoneStatus.decided if due < today else MilestoneStatus.due,
                    ))

            # --- thesis (later-stage students only) -----------------------------------------
            if status in (StudentStatus.completed,) or (today - start).days > 900:
                s.add(Thesis(
                    student_id=student.id, title=f"A study of {rng.choice(AREAS).lower()}",
                    status=ThesisStatus.approved if status is StudentStatus.completed
                    else rng.choice([ThesisStatus.preparation, ThesisStatus.submitted,
                                     ThesisStatus.under_examination, ThesisStatus.corrections]),
                ))

            # --- suspension ------------------------------------------------------------------
            if status is StudentStatus.active and rng.random() < P_SUSPENDED:
                sus_start = today - timedelta(days=rng.randint(20, 120))
                s.add(StudentLifecycleEvent(
                    student_id=student.id, event_type=LifecycleEventType.suspension,
                    status=LifecycleEventStatus.approved,
                    start_date=sus_start, end_date=today + timedelta(days=rng.randint(30, 120)),
                    reason="Medical leave (generated for UAT).",
                    days_applied=(today - sus_start).days,
                ))
                student.status = StudentStatus.suspended
                planted["suspended_student"] += 1

            if (i + 1) % 25 == 0:
                await s.commit()
        await s.commit()

    print(f"\nGenerated {n_students} students (prefix {prefix}, seed {seed}).")
    print("\nDeliberately planted problems — the integrity reports should find exactly these:")
    for k, v in sorted(planted.items()):
        print(f"  {v:4d}  {k}")
    print("\nVerify with:")
    print("  GET /api/v1/reports/funding-integrity")
    print("  Ask PGR: 'students with no supervision meeting in 90 days'")
    print("  Ask PGR: 'students with an overdue milestone'")
    print("\nExpect detected counts to be LOWER than planted: the integrity and cohort reports")
    print("only examine registered/active students, and this cohort deliberately includes")
    print("completed, withdrawn and suspended ones. Any pre-existing students in the database")
    print("also contribute findings of their own.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate a representative PGR cohort for UAT.")
    ap.add_argument("--students", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--prefix", default="UAT")
    ap.add_argument("--clean", action="store_true",
                    help="remove a previous cohort with this prefix first (repeatable runs)")
    args = ap.parse_args()
    asyncio.run(main(args.students, args.seed, args.prefix, args.clean))
