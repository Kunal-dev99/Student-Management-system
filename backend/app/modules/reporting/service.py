"""Reporting service — composes dashboard read models (arch §13.3)."""
from __future__ import annotations

from app.modules.reporting.repository import ReportingRepository


class ReportingService:
    def __init__(self, repo: ReportingRepository) -> None:
        self.repo = repo

    async def executive(self) -> dict:
        totals = await self.repo.totals()
        students = await self.repo.students_by_status()
        stages = await self.repo.applications_by_stage()
        theses = await self.repo.theses_by_status()

        total_apps = sum(stages.values())
        converted = stages.get("converted", 0)
        active = students.get("registered", 0) + students.get("active", 0)
        completed = students.get("completed", 0)
        theses_submitted = theses.get("submitted", 0) + theses.get("under_examination", 0)

        return {
            "totals": totals,
            "activeResearchers": active,
            "completions": completed,
            "conversionRatePct": round((converted / total_apps) * 100, 1) if total_apps else 0.0,
            "applicationsInPipeline": total_apps,
            "fundedStudents": await self.repo.funded_students(),
            "thesesSubmitted": theses_submitted,
            "thesesApproved": theses.get("approved", 0),
            "applicationsByStage": stages,
            "studentsByStatus": students,
        }

    async def supervisor(self, person_id) -> dict:
        """Supervisor caseload with per-student status + risk flag (arch §13.3).

        Risk = an overdue in-progress milestone, or no active funding.
        """
        from datetime import date

        from app.modules.funding.repository import FundingRepository
        from app.modules.person.repository import PersonRepository
        from app.modules.person.service import PersonService
        from app.modules.progression.constants import MilestoneStatus
        from app.modules.progression.repository import ProgressionRepository
        from app.modules.student_record.repository import StudentRepository
        from app.modules.supervision.repository import SupervisionRepository

        session = self.repo.session
        if person_id is None:
            return {"caseload": []}
        student_ids = await SupervisionRepository(session).active_student_ids_for_supervisor(person_id)
        st_repo = StudentRepository(session)
        prog_repo = ProgressionRepository(session)
        fund_repo = FundingRepository(session)
        person_svc = PersonService(PersonRepository(session))

        caseload = []
        for sid in student_ids:
            student = await st_repo.get(sid)
            if student is None:
                continue
            person = await person_svc.get_person(student.person_id)

            milestones = await prog_repo.milestones_for_student(sid)
            current = next((m for m in milestones if m.status != MilestoneStatus.decided), None)
            current_name = None
            current_status = None
            overdue = False
            if current is not None:
                defn = await prog_repo.get_definition(current.milestone_definition_id)
                current_name = defn.name if defn else "Milestone"
                current_status = current.status.value
                overdue = bool(current.due_date and current.due_date < date.today())

            has_funding = any(a.valid_to is None for a in await fund_repo.arrangements_for_student(sid))
            reasons = []
            if overdue:
                reasons.append("milestone overdue")
            if not has_funding:
                reasons.append("no active funding")

            caseload.append({
                "studentId": sid,
                "studentRef": student.student_ref,
                "personName": f"{person.given_name} {person.family_name}",
                "status": student.status.value,
                "currentMilestone": current_name,
                "milestoneStatus": current_status,
                "funding": "active" if has_funding else "none",
                "risk": bool(reasons),
                "riskReasons": reasons,
            })
        return {"caseload": caseload}

    async def administrator(self) -> dict:
        stages = await self.repo.applications_by_stage()
        offers = await self.repo.offers_by_status()
        milestones = await self.repo.milestones_by_status()
        theses = await self.repo.theses_by_status()

        return {
            "applicationsAwaitingAssessment": stages.get("applicant", 0) + stages.get("under_assessment", 0),
            "offersAwaitingAcceptance": offers.get("issued", 0),
            "progressionReviewsDue": milestones.get("submitted", 0) + milestones.get("under_review", 0),
            "milestonesOverdue": milestones.get("overdue", 0),
            "thesesSubmitted": theses.get("submitted", 0) + theses.get("under_examination", 0),
            "pipelineByStage": stages,
        }
