"""Idempotent dev seed: roles, permissions, a demo admin user, and sample persons.

Run with:  python -m app.db.seed
Login after seeding:  admin@pgr.local / admin123   (dev only — change for real use)
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.core.database import SessionFactory
from app.core.security import hash_password
from app.modules.admissions.models import Offer
from app.modules.identity.constants import PERMISSIONS, ROLES
from app.modules.identity.models import Permission, Role, User
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.models import Person, PersonRelationship
from app.modules.recruitment.constants import ApplicationRoute, CandidateStage, OpportunityStatus
from app.modules.recruitment.models import Application, CandidateStageHistory, ResearchOpportunity
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.models import Department, Programme, ResearchArea, Student
from app.modules.supervision.constants import SupervisionStatus, SupervisorRole
from app.modules.supervision.models import SupervisorRelationship
from app.modules.progression.models import MilestoneDefinition
from app.modules.funding.constants import FundingStatus, FundingType
from app.modules.funding.models import FundingArrangement, FundingSource
from app.modules.workflow.models import Task, WorkflowDefinition

DEMO_EMAIL = "admin@example.com"
DEMO_PASSWORD = "admin123"


async def _seed_rbac(session) -> dict[str, Permission]:
    perms: dict[str, Permission] = {}
    for code, desc in PERMISSIONS.items():
        existing = (
            await session.execute(select(Permission).where(Permission.code == code))
        ).scalar_one_or_none()
        if existing is None:
            existing = Permission(code=code, description=desc)
            session.add(existing)
        perms[code] = existing
    await session.flush()

    for name, codes in ROLES.items():
        role = (
            await session.execute(select(Role).where(Role.name == name))
        ).scalar_one_or_none()
        if role is None:
            role = Role(name=name, description=f"{name} role")
            session.add(role)
            await session.flush()
        # Load the collection in async context before reassigning (avoids MissingGreenlet).
        await session.refresh(role, ["permissions"])
        role.permissions = list(perms.values()) if codes == ["*"] else [perms[c] for c in codes]
    await session.flush()
    return perms


async def _seed_admin(session) -> None:
    user = (
        await session.execute(select(User).where(User.email == DEMO_EMAIL))
    ).scalar_one_or_none()
    roles = (
        await session.execute(
            select(Role).where(Role.name.in_(["Institution Administrator", "PGR Administrator"]))
        )
    ).scalars().all()
    if user is None:
        user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD), is_active=True)
        session.add(user)
        await session.flush()
    await session.refresh(user, ["roles"])
    user.roles = list(roles)


async def _seed_persons(session) -> None:
    count = (await session.execute(select(Person))).scalars().first()
    if count is not None:
        return  # already seeded

    # A person who went applicant -> student -> alumni (shows the timeline).
    p1 = Person(
        given_name="Aisha", family_name="Khan", preferred_name="Aisha",
        email="aisha.khan@example.ac.uk", nationality="British",
        date_of_birth=date(1996, 4, 12),
    )
    p1.relationships = [
        PersonRelationship(
            relationship_type=PersonRelationshipType.applicant,
            valid_from=date(2020, 1, 15), valid_to=date(2020, 9, 30),
            source_system="recruitment",
        ),
        PersonRelationship(
            relationship_type=PersonRelationshipType.student,
            valid_from=date(2020, 10, 1), valid_to=date(2024, 6, 30),
            source_system="student_record",
        ),
        PersonRelationship(
            relationship_type=PersonRelationshipType.alumni,
            valid_from=date(2024, 7, 1), valid_to=None, source_system="completion",
        ),
    ]

    p2 = Person(
        given_name="Marcus", family_name="Bell", email="marcus.bell@example.ac.uk",
        nationality="Irish",
    )
    p2.relationships = [
        PersonRelationship(
            relationship_type=PersonRelationshipType.applicant,
            valid_from=date(2025, 2, 1), valid_to=None, source_system="recruitment",
        )
    ]

    session.add_all([p1, p2])
    await session.flush()


async def _seed_academic(session):
    if (await session.execute(select(Department))).scalars().first() is not None:
        return
    dept = Department(name="Computer Science", code="CS")
    session.add(dept)
    await session.flush()
    session.add_all([
        ResearchArea(name="Machine Learning", code="CS-ML", department_id=dept.id),
        Programme(name="PhD Computer Science", code="PHD-CS", department_id=dept.id),
    ])
    await session.flush()


async def _seed_recruitment(session):
    if (await session.execute(select(ResearchOpportunity))).scalars().first() is not None:
        return
    dept = (await session.execute(select(Department))).scalars().first()
    area = (await session.execute(select(ResearchArea))).scalars().first()
    # An open opportunity.
    opp = ResearchOpportunity(
        title="PhD in Machine Learning for Healthcare",
        research_area_id=area.id if area else None,
        department_id=dept.id if dept else None,
        stipend_amount=19000, currency="GBP",
        eligibility="2:1 or higher in a relevant discipline",
        expected_duration_months=42, positions_available=1,
        status=OpportunityStatus.open,
    )
    session.add(opp)
    await session.flush()
    # Marcus Bell (seeded as an applicant) applies to it.
    marcus = (
        await session.execute(select(Person).where(Person.email == "marcus.bell@example.ac.uk"))
    ).scalar_one_or_none()
    if marcus:
        app = Application(
            person_id=marcus.id, route=ApplicationRoute.opportunity_led,
            research_opportunity_id=opp.id, current_stage=CandidateStage.applicant,
        )
        app.history.append(
            CandidateStageHistory(
                from_stage=None, to_stage=CandidateStage.applicant,
                moved_at=datetime.now(timezone.utc),
            )
        )
        session.add(app)
    await session.flush()


async def _seed_supervisor(session):
    """A supervisor user linked to a person, assigned to one student — demonstrates row scoping.
    Login: elena.ford@example.com / super123 (sees only their supervisees)."""
    existing = (
        await session.execute(select(User).where(User.email == "elena.ford@example.com"))
    ).scalar_one_or_none()
    if existing is not None:
        return
    sup_role = (
        await session.execute(select(Role).where(Role.name == "Supervisor"))
    ).scalar_one_or_none()
    if sup_role is None:
        return
    elena = Person(given_name="Elena", family_name="Ford", email="elena.ford@example.com", nationality="British")
    session.add(elena)
    await session.flush()
    user = User(email="elena.ford@example.com", password_hash=hash_password("super123"), is_active=True, person_id=elena.id)
    session.add(user)
    await session.flush()
    await session.refresh(user, ["roles"])
    user.roles = [sup_role]

    # Assign Elena as primary supervisor to the first existing student (if any).
    student = (await session.execute(select(Student).limit(1))).scalar_one_or_none()
    if student is not None:
        session.add(SupervisorRelationship(
            student_id=student.id, supervisor_person_id=elena.id,
            role=SupervisorRole.primary, status=SupervisionStatus.active,
            valid_from=date.today(), valid_to=None,
        ))
    await session.flush()


async def _seed_milestone_definitions(session):
    """One configurable progression flow for the PhD programme (arch §8.8, §21)."""
    if (await session.execute(select(MilestoneDefinition))).scalars().first() is not None:
        return
    prog = (
        await session.execute(select(Programme).where(Programme.code == "PHD-CS"))
    ).scalar_one_or_none()
    if prog is None:
        return
    outcomes = ["progress", "progress_with_conditions", "further_review", "withdraw"]
    session.add_all([
        MilestoneDefinition(
            programme_id=prog.id, name="Induction Review", due_offset_days=30,
            trigger={"monthsAfter": "registration", "months": 1},
            possible_outcomes={"allowed": outcomes},
        ),
        MilestoneDefinition(
            programme_id=prog.id, name="Confirmation Review", due_offset_days=270,
            trigger={"monthsAfter": "registration", "months": 9},
            possible_outcomes={"allowed": outcomes + ["transfer_award"]},
        ),
        MilestoneDefinition(
            programme_id=prog.id, name="Annual Progress Review", due_offset_days=540,
            trigger={"monthsAfter": "registration", "months": 18},
            possible_outcomes={"allowed": outcomes},
        ),
    ])
    await session.flush()


async def _seed_funding(session):
    """Funding sources + one active arrangement for the first student (arch §8.9)."""
    if (await session.execute(select(FundingSource))).scalars().first() is not None:
        return
    epsrc = FundingSource(name="UKRI EPSRC", funder_type="research_council")
    scholarship = FundingSource(name="University Scholarship Fund", funder_type="university")
    session.add_all([epsrc, scholarship])
    await session.flush()
    student = (await session.execute(select(Student).limit(1))).scalar_one_or_none()
    if student is not None:
        session.add(FundingArrangement(
            student_id=student.id, funding_type=FundingType.research_council,
            funding_source_id=epsrc.id, stipend_amount=19000, currency="GBP",
            valid_from=date.today(), valid_to=None, status=FundingStatus.active,
        ))
    await session.flush()


async def _seed_tasks(session):
    """A couple of demo tasks so the inbox has content (real ones are created by triggers)."""
    if (await session.execute(select(Task))).scalars().first() is not None:
        return
    student = (await session.execute(select(Student).limit(1))).scalar_one_or_none()
    session.add_all([
        Task(
            title="Onboard newly registered PGR student", assignee_role="PGR Administrator",
            aggregate_type="student", aggregate_id=student.id if student else None,
        ),
        Task(
            title="Review Confirmation Review submission", assignee_role="Supervisor",
        ),
    ])
    await session.flush()


async def _seed_student_user(session):
    """A student login linked to a registered student's person (for the student portal).
    Login: <their email> / student123."""
    student = (
        await session.execute(
            select(Student).where(Student.status == StudentStatus.registered).limit(1)
        )
    ).scalar_one_or_none()
    if student is None:
        return
    person = (await session.execute(select(Person).where(Person.id == student.person_id))).scalar_one_or_none()
    if person is None or person.email is None:
        return
    existing = (await session.execute(select(User).where(User.email == person.email))).scalar_one_or_none()
    if existing is not None:
        return
    student_role = (await session.execute(select(Role).where(Role.name == "Student"))).scalar_one_or_none()
    if student_role is None:
        return
    user = User(email=person.email, password_hash=hash_password("student123"), is_active=True, person_id=person.id)
    session.add(user)
    await session.flush()
    await session.refresh(user, ["roles"])
    user.roles = [student_role]
    global STUDENT_LOGIN
    STUDENT_LOGIN = person.email


STUDENT_LOGIN = "(none)"


async def _seed_workflow(session):
    """A demo, data-defined workflow (arch §9.1) so the admin has something to see/advance."""
    if (await session.execute(select(WorkflowDefinition))).scalars().first() is not None:
        return
    session.add(WorkflowDefinition(
        key="onboarding", version=1, name="Student onboarding", initial_state="pending",
        states=["pending", "in_progress", "complete"],
        transitions=[
            {"from": "pending", "on": "start", "to": "in_progress",
             "action": {"createTask": {"title": "Complete onboarding checklist", "assigneeRole": "PGR Administrator"}}},
            {"from": "in_progress", "on": "finish", "to": "complete"},
        ],
        active=True,
    ))
    await session.flush()


async def main() -> None:
    async with SessionFactory() as session:
        await _seed_rbac(session)
        await _seed_admin(session)
        await _seed_persons(session)
        await _seed_academic(session)
        await _seed_recruitment(session)
        await _seed_supervisor(session)
        await _seed_milestone_definitions(session)
        await _seed_funding(session)
        await _seed_tasks(session)
        await _seed_student_user(session)
        await _seed_workflow(session)
        await session.commit()
    print(f"Seeded. Admin: {DEMO_EMAIL} / {DEMO_PASSWORD}  |  Supervisor: elena.ford@example.com / super123  |  Student: {STUDENT_LOGIN} / student123")


if __name__ == "__main__":
    asyncio.run(main())
