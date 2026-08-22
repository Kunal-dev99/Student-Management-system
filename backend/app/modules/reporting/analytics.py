"""Phase 3 analytics read models (arch §13.2, §13.3).

PGR Enterprise 360 — one population seen through five lenses (Student, Research, Funding,
Workforce, Statutory) — plus risk & completion analytics. Read-only; served off the read path.
In production these are materialized views refreshed on a schedule; here they are computed on
demand (kept portable, D-04).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.completion.constants import CompletionStatus
from app.modules.completion.models import Completion
from app.modules.funding.constants import FundingStatus
from app.modules.funding.models import FundingArrangement, FundingSource
from app.modules.person.constants import PersonRelationshipType
from app.modules.person.models import Person, PersonRelationship
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.models import Programme, ResearchArea, ResearchProject, Student

ACTIVE_STATES = {StudentStatus.registered, StudentStatus.active}


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _load(self):
        s = self.session
        rows = (await s.execute(select(Student, Person).join(Person, Person.id == Student.person_id))).all()
        projects = {p.student_id: p for p in (await s.execute(select(ResearchProject))).scalars().all()}
        areas = {a.id: a.name for a in (await s.execute(select(ResearchArea))).scalars().all()}
        programmes = {p.id: p.name for p in (await s.execute(select(Programme))).scalars().all()}
        sources = {f.id: f.name for f in (await s.execute(select(FundingSource))).scalars().all()}
        funding: dict = {}
        for fa in (await s.execute(select(FundingArrangement).where(
            FundingArrangement.status == FundingStatus.active, FundingArrangement.valid_to.is_(None)
        ))).scalars().all():
            funding.setdefault(fa.student_id, fa)
        employees = {
            r[0] for r in (await s.execute(select(PersonRelationship.person_id).where(
                PersonRelationship.relationship_type == PersonRelationshipType.employee,
                PersonRelationship.valid_to.is_(None),
            ))).all()
        }
        # student_ids with an overdue, undecided milestone
        overdue = {
            m.student_id for m in (await s.execute(select(Milestone).where(
                Milestone.status != MilestoneStatus.decided, Milestone.due_date.is_not(None),
                Milestone.due_date < date.today(),
            ))).scalars().all()
        }
        completions = {c.student_id: c for c in (await s.execute(select(Completion))).scalars().all()}
        # Phase 6.2 — how each student entered: opportunity-led (a funded position) or student-led
        # (their own proposal). Keyed by person, since one person carries one identity thread.
        from app.modules.recruitment.models import Application

        routes: dict = {}
        for a in (await s.execute(select(Application))).scalars().unique().all():
            routes.setdefault(a.person_id, a.route.value if hasattr(a.route, "value") else a.route)
        return rows, projects, areas, programmes, sources, funding, employees, overdue, completions, routes

    async def enterprise_360(self) -> dict:
        rows, projects, areas, programmes, sources, funding, employees, _overdue, _c, routes = await self._load()
        population = []
        for student, person in rows:
            proj = projects.get(student.id)
            fa = funding.get(student.id)
            population.append({
                "studentRef": student.student_ref,
                "personName": f"{person.given_name} {person.family_name}",
                "student": {"status": student.status.value, "studyMode": student.study_mode.value,
                            "startDate": student.start_date.isoformat() if student.start_date else None,
                            "entryRoute": routes.get(student.person_id)},
                "research": {"topic": proj.research_topic if proj else None,
                             "group": proj.research_group if proj else None,
                             "area": areas.get(student.research_area_id)},
                "funding": None if fa is None else {
                    "type": fa.funding_type.value, "source": sources.get(fa.funding_source_id),
                    "amount": str(fa.stipend_amount) if fa.stipend_amount is not None else None,
                    "currency": fa.currency},
                "workforce": {"isEmployee": person.id in employees},
                "statutory": {"nationality": person.nationality,
                              "programme": programmes.get(student.programme_id),
                              "expectedEnd": student.expected_end_date.isoformat() if student.expected_end_date else None},
            })
        summary = {
            "population": len(population),
            "funded": sum(1 for r in population if r["funding"]),
            "employees": sum(1 for r in population if r["workforce"]["isEmployee"]),
            "byStatus": _counter(r["student"]["status"] for r in population),
        }
        return {"summary": summary, "lenses": ["student", "research", "funding", "workforce", "statutory"],
                "population": population}

    async def analytics(self) -> dict:
        rows, _p, _a, _pr, _s, funding, _e, overdue, completions, _routes = await self._load()
        at_risk = []
        active = 0
        for student, person in rows:
            if student.status in ACTIVE_STATES:
                active += 1
                reasons = []
                if student.id in overdue:
                    reasons.append("milestone overdue")
                if student.id not in funding:
                    reasons.append("no active funding")
                if reasons:
                    at_risk.append({"studentRef": student.student_ref,
                                    "personName": f"{person.given_name} {person.family_name}",
                                    "reasons": reasons})

        graduated = [c for c in completions.values() if c.status == CompletionStatus.graduated]
        total_students = len(rows)
        completed = sum(1 for s, _ in rows if s.status == StudentStatus.completed)
        # avg time to completion (days) for graduated students
        durations = []
        student_by_id = {s.id: s for s, _ in rows}
        for c in graduated:
            st = student_by_id.get(c.student_id)
            if st and st.start_date and c.graduation_date:
                durations.append((c.graduation_date - st.start_date).days)
        avg_days = round(sum(durations) / len(durations)) if durations else None

        return {
            "risk": {
                "atRiskCount": len(at_risk),
                "activeStudents": active,
                "atRiskRatePct": round((len(at_risk) / active) * 100, 1) if active else 0.0,
                "students": at_risk,
            },
            "completion": {
                "completed": completed,
                "totalStudents": total_students,
                "completionRatePct": round((completed / total_students) * 100, 1) if total_students else 0.0,
                "avgTimeToCompletionDays": avg_days,
            },
            "forecast": {
                # Simple, explainable projection: active students not currently at risk are "on track".
                "onTrack": active - len(at_risk),
                "atRisk": len(at_risk),
                "note": "Rule-based projection: active students with no risk flag are on track.",
            },
        }


def _counter(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out
