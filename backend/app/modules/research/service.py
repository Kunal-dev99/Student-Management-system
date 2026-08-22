"""Research context business rules (Phase 6.1 — CIO vision GAP-01).

Two responsibilities:
1. Hold **award references** (mastered in the Research system; editable here only when no
   integration supplies them) and **research demand** (the need for a researcher).
2. Answer the lineage question the CIO asked for: *where did this position come from, and who did
   it produce?* — `Award → Demand → Position → Applications → Students`.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.modules.research.constants import (
    DEMAND_TRANSITIONS,
    EXTERNALLY_MASTERED_MESSAGE,
    AwardStatus,
    DemandStatus,
)
from app.modules.research.models import ResearchAward, ResearchDemand
from app.modules.research.repository import ResearchRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchService:
    def __init__(self, repo: ResearchRepository) -> None:
        self.repo = repo
        self.session = repo.session

    # ---------------- awards ----------------

    @staticmethod
    def award_out(a: ResearchAward) -> dict:
        return {
            "id": str(a.id), "awardRef": a.award_ref, "title": a.title,
            "funderId": str(a.funder_id) if a.funder_id else None,
            "principalInvestigatorId": str(a.principal_investigator_id) if a.principal_investigator_id else None,
            "startDate": a.start_date.isoformat() if a.start_date else None,
            "endDate": a.end_date.isoformat() if a.end_date else None,
            "value": str(a.value) if a.value is not None else None,
            "currency": a.currency,
            "status": a.status.value if hasattr(a.status, "value") else a.status,
            "sourceSystem": a.source_system,
            "externalRef": a.external_ref,
            # Externally-mastered awards are read-only here — the UI should not offer an edit form.
            "readOnly": a.source_system is not None,
        }

    async def list_awards(self) -> list[dict]:
        return [self.award_out(a) for a in await self.repo.list_awards()]

    async def get_award(self, award_id: uuid.UUID) -> ResearchAward:
        a = await self.repo.get_award(award_id)
        if a is None:
            raise NotFoundError("Research award not found")
        return a

    async def create_award(
        self, *, award_ref: str, title: str, funder_id: uuid.UUID | None = None,
        principal_investigator_id: uuid.UUID | None = None,
        start_date: date | None = None, end_date: date | None = None,
        value: Decimal | None = None, currency: str | None = None,
        source_system: str | None = None, external_ref: str | None = None,
    ) -> ResearchAward:
        """Manual fallback for institutions with no Research-system integration yet."""
        if await self.repo.get_award_by_ref(award_ref):
            raise ConflictError(f"An award with reference '{award_ref}' already exists")
        if start_date and end_date and end_date < start_date:
            raise WorkflowError("The award end date cannot precede its start date")
        award = ResearchAward(
            award_ref=award_ref, title=title, funder_id=funder_id,
            principal_investigator_id=principal_investigator_id,
            start_date=start_date, end_date=end_date, value=value, currency=currency,
            status=AwardStatus.active, source_system=source_system, external_ref=external_ref,
            synced_at=_now() if source_system else None,
        )
        self.repo.add(award)
        await self.session.commit()
        await self.session.refresh(award)
        return award

    async def upsert_from_research_system(self, payload: dict, *, system: str = "research") -> ResearchAward:
        """Apply an award record arriving from the Research system (integration hub).

        The external system is the source of truth, so this overwrites local values.
        """
        ref = str(payload.get("awardRef") or "").strip()
        if not ref:
            raise WorkflowError("awardRef is required")
        award = await self.repo.get_award_by_ref(ref)
        if award is None:
            award = ResearchAward(award_ref=ref, title=payload.get("title") or ref)
            self.repo.add(award)
        award.title = payload.get("title") or award.title
        for field, key in (("start_date", "startDate"), ("end_date", "endDate")):
            if payload.get(key):
                setattr(award, field, date.fromisoformat(payload[key]))
        if payload.get("value") is not None:
            award.value = Decimal(str(payload["value"]))
        award.currency = payload.get("currency") or award.currency
        award.source_system = system
        award.external_ref = payload.get("externalRef") or award.external_ref
        award.synced_at = _now()
        await self.session.commit()
        await self.session.refresh(award)
        return award

    async def update_award(self, award_id: uuid.UUID, patch: dict) -> ResearchAward:
        award = await self.get_award(award_id)
        if award.source_system:
            # Guardrail: we hold a reference, not the authority (this is not grants management).
            raise ConflictError(EXTERNALLY_MASTERED_MESSAGE.format(system=award.source_system))
        for key, value in patch.items():
            if value is not None:
                setattr(award, key, value)
        await self.session.commit()
        await self.session.refresh(award)
        return award

    # ---------------- demand ----------------

    @staticmethod
    def demand_out(d: ResearchDemand) -> dict:
        return {
            "id": str(d.id), "title": d.title,
            "researchAwardId": str(d.research_award_id) if d.research_award_id else None,
            "researchAreaId": str(d.research_area_id) if d.research_area_id else None,
            "departmentId": str(d.department_id) if d.department_id else None,
            "requestedPlaces": d.requested_places,
            "justification": d.justification,
            "targetStartDate": d.target_start_date.isoformat() if d.target_start_date else None,
            "status": d.status.value if hasattr(d.status, "value") else d.status,
        }

    async def list_demands(self, status: str | None = None) -> list[dict]:
        return [self.demand_out(d) for d in await self.repo.list_demands(status)]

    async def get_demand(self, demand_id: uuid.UUID) -> ResearchDemand:
        d = await self.repo.get_demand(demand_id)
        if d is None:
            raise NotFoundError("Research demand not found")
        return d

    async def create_demand(
        self, *, title: str, research_award_id: uuid.UUID | None = None,
        research_area_id: uuid.UUID | None = None, department_id: uuid.UUID | None = None,
        requested_places: int = 1, justification: str | None = None,
        target_start_date: date | None = None, raised_by_user_id: uuid.UUID | None = None,
    ) -> ResearchDemand:
        if requested_places < 1:
            raise WorkflowError("A demand must request at least one place")
        if research_award_id is not None:
            await self.get_award(research_award_id)   # must exist
        demand = ResearchDemand(
            title=title, research_award_id=research_award_id, research_area_id=research_area_id,
            department_id=department_id, requested_places=requested_places,
            justification=justification, target_start_date=target_start_date,
            raised_by_user_id=raised_by_user_id,
        )
        self.repo.add(demand)
        await self.session.commit()
        await self.session.refresh(demand)
        return demand

    async def transition_demand(self, demand_id: uuid.UUID, to_status: DemandStatus) -> ResearchDemand:
        demand = await self.get_demand(demand_id)
        allowed = DEMAND_TRANSITIONS.get(demand.status, set())
        if to_status not in allowed:
            names = ", ".join(sorted(s.value for s in allowed)) or "nothing (terminal)"
            raise WorkflowError(
                f"Cannot move demand from '{demand.status.value}' to '{to_status.value}'. Allowed: {names}"
            )
        demand.status = to_status
        await self.session.commit()
        await self.session.refresh(demand)
        return demand

    # ---------------- lineage ----------------

    async def position_lineage(self, opportunity_id: uuid.UUID) -> dict:
        """Answer: where did this position come from, and who did it produce?

        Award → Demand → Position → Applications → Students. Every hop is optional, and a missing
        hop is reported rather than hidden, so a broken chain is visible.
        """
        from app.modules.person.models import Person
        from app.modules.recruitment.models import Application, ResearchOpportunity
        from app.modules.student_record.models import Student

        opp = (await self.session.execute(
            select(ResearchOpportunity).where(ResearchOpportunity.id == opportunity_id)
        )).scalar_one_or_none()
        if opp is None:
            raise NotFoundError("Research opportunity not found")

        demand = await self.repo.get_demand(opp.research_demand_id) if opp.research_demand_id else None
        award_id = opp.research_award_id or (demand.research_award_id if demand else None)
        award = await self.repo.get_award(award_id) if award_id else None

        funder = None
        if award and award.funder_id:
            from app.modules.funding.models import FundingSource

            src = (await self.session.execute(
                select(FundingSource).where(FundingSource.id == award.funder_id)
            )).scalar_one_or_none()
            funder = {"id": str(src.id), "name": src.name} if src else None

        rows = (await self.session.execute(
            select(Application).where(Application.research_opportunity_id == opportunity_id)
        )).scalars().unique().all()

        applications = []
        for a in rows:
            student = (await self.session.execute(
                select(Student, Person).join(Person, Person.id == Student.person_id)
                .where(Student.person_id == a.person_id)
            )).first()
            applications.append({
                "applicationId": str(a.id),
                "route": a.route.value if hasattr(a.route, "value") else a.route,
                "stage": a.current_stage.value if hasattr(a.current_stage, "value") else a.current_stage,
                "student": {
                    "studentId": str(student[0].id), "studentRef": student[0].student_ref,
                    "personName": f"{student[1].given_name} {student[1].family_name}",
                    "link": f"/students/{student[0].id}",
                } if student else None,
            })

        gaps = []
        if demand is None:
            gaps.append("This position is not linked to a research demand.")
        if award is None:
            gaps.append("No research award is linked, so funding provenance cannot be traced.")
        elif funder is None:
            gaps.append("The linked award has no funder recorded.")

        return {
            "award": self.award_out(award) if award else None,
            "funder": funder,
            "demand": self.demand_out(demand) if demand else None,
            "position": {
                "id": str(opp.id), "title": opp.title,
                "status": opp.status.value if hasattr(opp.status, "value") else opp.status,
                "positionsAvailable": opp.positions_available,
                "positionsFilled": opp.positions_filled,
                "positionsRemaining": max(0, opp.positions_available - opp.positions_filled),
                "expectedDurationMonths": opp.expected_duration_months,
            },
            "applications": applications,
            "studentsProduced": sum(1 for a in applications if a["student"]),
            "gaps": gaps,
        }
