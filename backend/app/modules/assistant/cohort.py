"""Composable cohort queries (Phase 5.1) — the capability the UI has no screen for.

Answers questions like *"students with no supervision meeting in 90 days AND funding expiring this
year"* by composing filters over the existing read models. Every result explains **why** it matched,
so the answer is auditable rather than an opaque list.

Row-scoping is honoured: the caller passes `allowed_ids` from `student_scope(principal)`, exactly as
the REST routers do, so the assistant can never widen a user's visibility.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.funding.constants import FundingStatus
from app.modules.funding.models import FundingArrangement
from app.modules.person.models import Person
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone, MilestoneDefinition
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.models import Programme, Student
from app.modules.supervision.models import SupervisionMeeting, SupervisorRelationship
from app.modules.thesis.models import Thesis

# Statuses that count as "currently studying".
ACTIVE_STATUSES = [StudentStatus.registered, StudentStatus.active]


class CohortQuery:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run(
        self,
        *,
        allowed_ids: list[uuid.UUID] | None = None,
        status: str | None = None,
        programme: str | None = None,
        supervisor_name: str | None = None,
        active_only: bool = True,
        no_supervision_meeting_in_days: int | None = None,
        funding_expiring_within_days: int | None = None,
        no_active_funding: bool = False,
        milestone_overdue: bool = False,
        thesis_status: str | None = None,
        limit: int = 50,
    ) -> dict:
        """Return {count, filters, students:[{...,'reasons':[...]}]}.

        Filters combine with AND. Each matched student carries the reasons it matched so the
        answer can be shown (and defended) row by row.
        """
        today = date.today()
        applied: list[str] = []

        stmt = select(Student, Person).join(Person, Person.id == Student.person_id)
        if allowed_ids is not None:
            stmt = stmt.where(Student.id.in_(allowed_ids))
        if status:
            stmt = stmt.where(Student.status == StudentStatus(status))
            applied.append(f"status = {status}")
        elif active_only:
            stmt = stmt.where(Student.status.in_(ACTIVE_STATUSES))
            applied.append("currently studying")

        if programme:
            prog_ids = (await self.session.execute(
                select(Programme.id).where(Programme.name.ilike(f"%{programme}%"))
            )).scalars().all()
            stmt = stmt.where(Student.programme_id.in_(list(prog_ids)))
            applied.append(f"programme ~ {programme}")

        if supervisor_name:
            sup_ids = (await self.session.execute(
                select(Person.id).where(
                    (Person.given_name + " " + Person.family_name).ilike(f"%{supervisor_name}%")
                )
            )).scalars().all()
            student_ids = (await self.session.execute(
                select(SupervisorRelationship.student_id).where(
                    SupervisorRelationship.supervisor_person_id.in_(list(sup_ids)),
                    SupervisorRelationship.valid_to.is_(None),
                )
            )).scalars().all()
            stmt = stmt.where(Student.id.in_(list(student_ids)))
            applied.append(f"supervised by ~ {supervisor_name}")

        rows = (await self.session.execute(stmt)).all()

        # --- post-filters that need per-student lookups (kept off the hot path above) ---
        results: list[dict] = []
        for student, person in rows:
            reasons: list[str] = []
            keep = True

            if no_supervision_meeting_in_days is not None:
                last = (await self.session.execute(
                    select(SupervisionMeeting.met_on)
                    .where(SupervisionMeeting.student_id == student.id)
                    .order_by(SupervisionMeeting.met_on.desc())
                    .limit(1)
                )).scalars().first()
                cutoff = today - timedelta(days=no_supervision_meeting_in_days)
                if last is None:
                    reasons.append("no supervision meeting ever recorded")
                elif last < cutoff:
                    reasons.append(f"last supervision meeting {(today - last).days} days ago ({last.isoformat()})")
                else:
                    keep = False
            if not keep:
                continue

            if funding_expiring_within_days is not None:
                horizon = today + timedelta(days=funding_expiring_within_days)
                expiring = (await self.session.execute(
                    select(FundingArrangement).where(
                        FundingArrangement.student_id == student.id,
                        FundingArrangement.status == FundingStatus.active,
                        FundingArrangement.valid_to.is_not(None),
                        FundingArrangement.valid_to >= today,
                        FundingArrangement.valid_to <= horizon,
                    )
                )).scalars().first()
                if expiring is None:
                    keep = False
                else:
                    reasons.append(f"funding expires {expiring.valid_to.isoformat()}")
            if not keep:
                continue

            if no_active_funding:
                active_funding = (await self.session.execute(
                    select(FundingArrangement).where(
                        FundingArrangement.student_id == student.id,
                        FundingArrangement.status == FundingStatus.active,
                        FundingArrangement.valid_to.is_(None),
                    )
                )).scalars().first()
                if active_funding is not None:
                    keep = False
                else:
                    reasons.append("no active funding arrangement")
            if not keep:
                continue

            if milestone_overdue:
                overdue = (await self.session.execute(
                    select(Milestone, MilestoneDefinition)
                    .join(MilestoneDefinition, MilestoneDefinition.id == Milestone.milestone_definition_id)
                    .where(
                        Milestone.student_id == student.id,
                        Milestone.due_date.is_not(None),
                        Milestone.due_date < today,
                        Milestone.status.notin_([MilestoneStatus.decided]),
                    )
                )).first()
                if overdue is None:
                    keep = False
                else:
                    m, defn = overdue
                    reasons.append(f"milestone '{defn.name}' overdue since {m.due_date.isoformat()}")
            if not keep:
                continue

            if thesis_status:
                thesis = (await self.session.execute(
                    select(Thesis).where(Thesis.student_id == student.id)
                )).scalars().unique().first()
                if thesis is None or thesis.status.value != thesis_status:
                    keep = False
                else:
                    reasons.append(f"thesis status = {thesis_status}")
            if not keep:
                continue

            results.append({
                "studentId": str(student.id),
                "studentRef": student.student_ref,
                "personName": f"{person.given_name} {person.family_name}",
                "status": student.status.value if hasattr(student.status, "value") else student.status,
                "reasons": reasons,
                "link": f"/students/{student.id}",
            })
            if len(results) >= limit:
                break

        for key, label in (
            (no_supervision_meeting_in_days, f"no supervision meeting in {no_supervision_meeting_in_days} days"),
            (funding_expiring_within_days, f"funding expiring within {funding_expiring_within_days} days"),
        ):
            if key is not None:
                applied.append(label)
        if no_active_funding:
            applied.append("no active funding")
        if milestone_overdue:
            applied.append("milestone overdue")
        if thesis_status:
            applied.append(f"thesis status = {thesis_status}")

        return {"count": len(results), "filters": applied, "students": results}
