"""Student portal read model (arch §13.3 — student journey).

Everything is resolved from the authenticated principal's person_id, so a student can only ever
see their own journey — there is no id in the URL to tamper with.
"""
from __future__ import annotations

from app.core.principal import Principal


class PortalService:
    def __init__(self, session) -> None:
        self.session = session

    async def student_journey(self, principal: Principal) -> dict:
        from app.modules.funding.repository import FundingRepository
        from app.modules.funding.service import FundingService
        from app.modules.person.repository import PersonRepository
        from app.modules.person.service import PersonService
        from app.modules.progression.repository import ProgressionRepository
        from app.modules.progression.service import ProgressionService
        from app.modules.student_record.repository import StudentRepository
        from app.modules.thesis.repository import ThesisRepository
        from app.modules.thesis.service import ThesisService

        person_id = principal.person_id
        if person_id is None:
            return {"linked": False, "person": None, "student": None}

        person_svc = PersonService(PersonRepository(self.session))
        person = await person_svc.get_person(person_id)
        timeline = await person_svc.timeline(person_id)

        result: dict = {
            "linked": True,
            "person": {
                "name": f"{person.given_name} {person.family_name}",
                "email": person.email,
                "timeline": [
                    {"label": e.label, "at": e.at.isoformat(), "kind": e.kind} for e in timeline
                ],
            },
            "student": None,
            "milestones": [],
            "funding": [],
            "thesis": None,
        }

        student = await StudentRepository(self.session).get_by_person(person_id)
        if student is None:
            return result

        result["student"] = {
            "id": str(student.id),
            "studentRef": student.student_ref,
            "status": student.status.value,
            "studyMode": student.study_mode.value,
            "startDate": student.start_date.isoformat() if student.start_date else None,
            "researchTopic": student.project.research_topic if student.project else None,
        }
        result["milestones"] = await ProgressionService(
            ProgressionRepository(self.session)
        ).list_milestones(student.id)
        arrangements = await FundingService(
            FundingRepository(self.session)
        ).list_arrangements(student.id)
        result["funding"] = [a for a in arrangements if a["validTo"] is None]
        thesis = await ThesisService(ThesisRepository(self.session)).get_for_student(student.id)
        if thesis is not None:
            result["thesis"] = {
                "status": thesis.status.value,
                "title": thesis.title,
                "submittedAt": thesis.submitted_at.isoformat() if thesis.submitted_at else None,
                "outcome": thesis.examination.outcome.value if thesis.examination and thesis.examination.outcome else None,
            }
        return result
