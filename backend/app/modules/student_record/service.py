"""Student record business rules (arch §6.1, §8.6)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from app.core.errors import ConflictError, NotFoundError
from app.modules.person.repository import PersonRepository
from app.modules.person.service import PersonService
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, ResearchProject, Student
from app.modules.student_record.repository import StudentRepository


def _generate_student_ref() -> str:
    year = datetime.now(timezone.utc).year
    return f"PGR-{year}-{uuid.uuid4().hex[:6].upper()}"


def _add_months(start: date, months: int) -> date:
    """Add whole months to a date, clamping the day to the target month's length."""
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    # Clamp (e.g. 31 Jan + 1 month -> 28/29 Feb).
    for day in (start.day, 28, 29, 30, 31):
        try:
            return date(year, month, min(day, start.day))
        except ValueError:
            continue
    return date(year, month, 28)


class StudentService:
    def __init__(self, repo: StudentRepository) -> None:
        self.repo = repo

    async def list_students(
        self, *, limit: int, offset: int, allowed_ids=None, search: str | None = None, status=None
    ):
        return await self.repo.list(
            limit=limit, offset=offset, allowed_ids=allowed_ids, search=search, status=status
        )

    async def get_student(self, student_id: uuid.UUID, *, allowed_ids=None) -> Student:
        student = await self.repo.get(student_id, allowed_ids=allowed_ids)
        if student is None:
            raise NotFoundError("Student not found")
        return student

    async def person_has_application(self, person_id: uuid.UUID) -> bool:
        """True if this person came through recruitment (has an application) — as opposed to a
        direct enrolment (ICR G2). Used to decide whether the journey has an 'Applicant' stage.

        A real recruitment journey always leaves a trail of ``CandidateStageHistory`` rows (one
        per stage transition), so we require at least one history entry. This deliberately excludes
        synthetic Applications created by data-fixup scripts (which stamp a single Application
        row and no history just to populate the ENTRYROUTE field on the HESA return) — those
        must not turn a direct-enrolment student into a funnel entrant on the journey tracker.
        """
        from sqlalchemy import exists, select

        from app.modules.recruitment.models import Application, CandidateStageHistory

        return bool((await self.repo.session.execute(
            select(exists().where(
                Application.person_id == person_id,
                exists().where(CandidateStageHistory.application_id == Application.id).correlate(Application),
            ))
        )).scalar())

    async def update_student(self, student_id: uuid.UUID, patch: dict) -> Student:
        student = await self.get_student(student_id)
        for key, value in patch.items():
            setattr(student, key, value)
        await self.repo.session.commit()
        await self.repo.session.refresh(student)
        return student

    # --- Programme administration (ICR G3) ---
    async def list_programmes(self) -> list[Programme]:
        return await self.repo.list_programmes()

    async def create_programme(self, data) -> Programme:
        if await self.repo.get_programme_by_code(data.code):
            raise ConflictError(f"A programme with code '{data.code}' already exists")
        prog = Programme(**data.model_dump())
        self.repo.session.add(prog)
        await self.repo.session.commit()
        await self.repo.session.refresh(prog)
        return prog

    async def update_programme(self, programme_id: uuid.UUID, patch: dict) -> Programme:
        prog = await self.repo.get_programme(programme_id)
        if prog is None:
            raise NotFoundError("Programme not found")
        new_code = patch.get("code")
        if new_code and new_code != prog.code and await self.repo.get_programme_by_code(new_code):
            raise ConflictError(f"A programme with code '{new_code}' already exists")
        for key, value in patch.items():
            setattr(prog, key, value)
        await self.repo.session.commit()
        await self.repo.session.refresh(prog)
        return prog

    async def create_from_application(
        self,
        *,
        person_id: uuid.UUID,
        programme_id: uuid.UUID | None,
        department_id: uuid.UUID | None,
        research_area_id: uuid.UUID | None,
        start_date: date | None,
        study_mode: StudyMode,
        research_topic: str | None,
        research_award_id: uuid.UUID | None = None,
        research_opportunity_id: uuid.UUID | None = None,
        status: StudentStatus = StudentStatus.registered,
        expected_end_date: date | None = None,
        student_ref: str | None = None,
    ) -> Student:
        """Create a student, REUSING the applicant's person_id (arch §8.6 key rule).

        ``status`` defaults to ``registered`` (the offer-acceptance path); the direct enrolment
        door (ICR G2) passes it explicitly so an accepted-but-not-yet-registered student can be
        recorded as ``prospective``. ``expected_end_date`` is optional here — the offer path
        derives it from the position's advertised duration; the enrol door may pass it directly.
        ``student_ref`` lets the cohort import carry the institution's own reference (so a re-run
        is idempotent on it); when omitted a ``PGR-<year>-<hex>`` reference is generated.
        """
        if await self.repo.get_by_person(person_id) is not None:
            raise ConflictError("This person is already a student")
        if programme_id is None:
            prog = await self.repo.first_programme()
            programme_id = prog.id if prog else None

        student = Student(
            person_id=person_id,
            student_ref=student_ref or _generate_student_ref(),
            programme_id=programme_id,
            department_id=department_id,
            research_area_id=research_area_id,
            start_date=start_date or date.today(),
            study_mode=study_mode,
            status=status,
        )
        if expected_end_date is not None:
            student.expected_end_date = expected_end_date
            student.original_expected_end_date = expected_end_date
        # Phase 6.3 — create the research project whenever there is anything to record against it,
        # carrying the award and originating position so the funding lineage works without anyone
        # having to link it by hand later.
        if research_topic or research_award_id or research_opportunity_id:
            student.project = ResearchProject(
                research_topic=research_topic,
                research_area_id=research_area_id,
                research_award_id=research_award_id,
                research_opportunity_id=research_opportunity_id,
                start_date=student.start_date,
            )
        await self.repo.add(student)
        return student

    async def enrol(
        self,
        *,
        person_id: uuid.UUID | None,
        person_data=None,
        programme_id: uuid.UUID | None,
        department_id: uuid.UUID | None = None,
        research_area_id: uuid.UUID | None = None,
        research_topic: str | None = None,
        start_date: date | None = None,
        study_mode: StudyMode = StudyMode.full_time,
        status: StudentStatus = StudentStatus.registered,
        expected_end_date: date | None = None,
        student_ref: str | None = None,
        funding=None,
    ) -> Student:
        """Enrol an already-accepted student directly — ICR G2.

        The entry point for institutions that run recruitment in a separate system: no
        opportunity/offer chain required. Either attach an existing ``person_id`` or supply
        ``person_data`` to create the Person, then create the Student and open a ``student``
        relationship (closing any lingering ``applicant`` one). Reuses ``create_from_application``
        for the student row itself so the enrol door and the offer door produce identical records.
        """
        from app.modules.person.constants import PersonRelationshipType

        person_service = PersonService(PersonRepository(self.repo.session))
        if person_id is None:
            if person_data is None:
                raise NotFoundError("Provide either an existing personId or new person details")
            person = await person_service.create_person(person_data)
            person_id = person.id
        else:
            await person_service.get_person(person_id)  # 404 if the person does not exist

        # ICR G3 — when no end date is supplied, derive it from the programme's expected duration
        # (part-time stretches it by the institution's part-time factor), so an enrolled student
        # has a baseline for suspensions/extensions to adjust later.
        if expected_end_date is None and programme_id is not None:
            prog = await self.repo.get_programme(programme_id)
            if prog is not None and prog.duration_months:
                months = prog.duration_months
                if study_mode is StudyMode.part_time:
                    from app.modules.student_record.constants import PART_TIME_FACTOR
                    months = int(months * PART_TIME_FACTOR)
                expected_end_date = _add_months(start_date or date.today(), months)

        student = await self.create_from_application(
            person_id=person_id,
            programme_id=programme_id,
            department_id=department_id,
            research_area_id=research_area_id,
            start_date=start_date,
            study_mode=study_mode,
            research_topic=research_topic,
            status=status,
            expected_end_date=expected_end_date,
            student_ref=student_ref,
        )
        # Preserve the identity thread: open a student relationship, closing an applicant one if
        # this person happened to have applied through us first (harmless no-op if they didn't).
        await person_service.transition_identity(
            person_id,
            end_type=PersonRelationshipType.applicant,
            open_type=PersonRelationshipType.student,
            source_system="enrolment",
        )
        if funding is not None:
            from app.modules.funding.repository import FundingRepository
            from app.modules.funding.service import FundingService

            await FundingService(
                FundingRepository(self.repo.session)
            ).create_arrangement(student.id, funding)

        await self.repo.session.commit()
        await self.repo.session.refresh(student)

        # ICR G3 — lay down the whole milestone schedule now, so a newly enrolled student shows
        # every expected milestone up front rather than one at a time. Safe for taught programmes
        # too (they simply have their own milestone templates, or none).
        from app.modules.progression.repository import ProgressionRepository
        from app.modules.progression.service import ProgressionService

        await ProgressionService(
            ProgressionRepository(self.repo.session)
        ).generate_full_schedule(student)

        # ICR G1 — a taught student's core modules flow in on enrol, the same way milestones do,
        # so the cohort is set up at the group level rather than module-by-module per student.
        from app.modules.taught.repository import TaughtRepository
        from app.modules.taught.service import TaughtService

        await TaughtService(TaughtRepository(self.repo.session)).enrol_core_modules(student)
        return student

    async def summary(self, student_id: uuid.UUID, *, allowed_ids=None) -> dict:
        from app.modules.funding.repository import FundingRepository
        from app.modules.funding.service import FundingService
        from app.modules.supervision.repository import SupervisionRepository
        from app.modules.supervision.service import SupervisionService

        student = await self.get_student(student_id, allowed_ids=allowed_ids)
        person_service = PersonService(PersonRepository(self.repo.session))
        person = await person_service.get_person(student.person_id)
        # ICR G1 — surface the programme type so the student-360 can pick the taught vs research
        # panel set. Defaults to research for any student whose programme is unset.
        from app.modules.student_record.constants import ProgrammeType
        from app.modules.student_record.models import Programme
        programme = await self.repo.session.get(Programme, student.programme_id) if student.programme_id else None
        programme_type = (programme.programme_type if programme else ProgrammeType.research)
        # ICR G4 — the student's current study intensity (FTE %), derived from approved
        # intensity changes (falls back to full/part-time when none recorded).
        from app.modules.student_record.lifecycle import LifecycleService
        current_intensity = await LifecycleService(self.repo.session)._current_intensity(student)
        supervisors = await SupervisionService(
            SupervisionRepository(self.repo.session)
        ).supervisors_for_student(student_id)
        active = [
            {"name": s["supervisorName"], "role": s["role"].value if hasattr(s["role"], "value") else s["role"]}
            for s in supervisors if s["validTo"] is None
        ]
        arrangements = await FundingService(
            FundingRepository(self.repo.session)
        ).list_arrangements(student_id, allowed_ids=allowed_ids)
        funding = [
            {
                "fundingType": a["fundingType"].value if hasattr(a["fundingType"], "value") else a["fundingType"],
                "stipendAmount": str(a["stipendAmount"]) if a["stipendAmount"] is not None else None,
                "currency": a["currency"],
                "source": a["fundingSourceName"],
            }
            for a in arrangements if a["validTo"] is None
        ]
        return {
            "id": student.id,
            "studentRef": student.student_ref,
            "personId": student.person_id,
            "personName": f"{person.given_name} {person.family_name}",
            "status": student.status,
            "studyMode": student.study_mode,
            "currentIntensityPct": current_intensity,
            "startDate": student.start_date,
            "programmeId": student.programme_id,
            "programmeType": programme_type,
            "programmeName": programme.name if programme else None,
            "researchTopic": student.project.research_topic if student.project else None,
            "supervisors": active,
            "funding": funding,
        }
