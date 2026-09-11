"""Supervisor's "My students" surface — the caseload enriched for the supervisor's own view.

The existing `/supervisors/{person_id}/caseload` endpoint returns caseload rows for any
supervisor (admin surface). This endpoint scopes to the calling principal — no id in the
URL to tamper with — and enriches each row with the two things a supervisor actually
wants at a glance:

- **Next milestone** — the earliest open milestone (name + due date + status)
- **Open flags** — same rule set the Weekly Review Queue uses, per student

A supervisor's Monday morning question ("who needs me today?") is answered by this one
call.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_principal
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.funding.constants import FundingStatus
from app.modules.funding.models import FundingArrangement
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone, MilestoneDefinition
from app.modules.student_record.models import Student
from app.modules.supervision.repository import SupervisionRepository
from app.modules.supervision.service import SupervisionService

router = APIRouter(prefix="/my", tags=["my-students"])


OPEN_MILESTONE_STATES = {
    MilestoneStatus.not_started,
    MilestoneStatus.due,
    MilestoneStatus.submitted,
    MilestoneStatus.under_review,
    MilestoneStatus.overdue,
}


@router.get("/students", summary="The calling supervisor's own caseload, enriched")
async def my_students(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    """One-call answer to "who needs me today?" — the supervisor's own students, each row
    carrying the next open milestone and the flags a supervisor cares about."""
    if principal.person_id is None:
        raise HTTPException(status_code=404, detail="No person record linked to this account")

    svc = SupervisionService(SupervisionRepository(session))
    rows = await svc.caseload(principal.person_id)
    if not rows:
        return {"students": [], "summary": {"total": 0, "flagged": 0}}

    today = date.today()

    # Batch-fetch the milestones and funding for every caseload student — one query
    # per lookup shape, not one per student.
    student_ids = [r["studentId"] for r in rows]
    milestones = (await session.execute(
        select(Milestone, MilestoneDefinition)
        .join(MilestoneDefinition, MilestoneDefinition.id == Milestone.milestone_definition_id)
        .where(Milestone.student_id.in_(student_ids))
    )).all()
    funding_by_student: dict[str, list[FundingArrangement]] = {}
    for fa in (await session.execute(
        select(FundingArrangement).where(FundingArrangement.student_id.in_(student_ids))
    )).scalars().all():
        funding_by_student.setdefault(str(fa.student_id), []).append(fa)

    expected_ends: dict[str, date | None] = {}
    for s in (await session.execute(
        select(Student).where(Student.id.in_(student_ids))
    )).scalars().all():
        expected_ends[str(s.id)] = s.expected_end_date

    # Bucket milestones by student and pick the earliest open one.
    milestones_by_student: dict[str, list[tuple[Milestone, MilestoneDefinition]]] = {}
    for m, mdef in milestones:
        milestones_by_student.setdefault(str(m.student_id), []).append((m, mdef))

    enriched = []
    flagged_count = 0
    for r in rows:
        sid = str(r["studentId"])
        # Next milestone — the open one with the closest due date, or the earliest if none has a date.
        opens = [
            (m, mdef) for m, mdef in milestones_by_student.get(sid, [])
            if m.status in OPEN_MILESTONE_STATES
        ]
        opens.sort(key=lambda pair: (pair[0].due_date is None, pair[0].due_date or date.max))
        next_milestone = None
        if opens:
            m, mdef = opens[0]
            next_milestone = {
                "name": mdef.name,
                "status": m.status.value,
                "dueDate": m.due_date.isoformat() if m.due_date else None,
                "daysUntilDue": (m.due_date - today).days if m.due_date else None,
            }

        # Flags — same rule set as the Weekly Review Queue.
        flags: list[str] = []
        overdue_count = sum(1 for m, _ in milestones_by_student.get(sid, [])
                            if m.status == MilestoneStatus.overdue)
        if overdue_count:
            flags.append(f"{overdue_count} milestone(s) overdue")
        if not any(f.status == FundingStatus.active for f in funding_by_student.get(sid, [])):
            flags.append("no active funding")
        end = expected_ends.get(sid)
        if end:
            days_left = (end - today).days
            if 0 <= days_left <= 90:
                flags.append(f"expected end in {days_left} days")
            elif days_left < 0:
                flags.append(f"past expected end by {-days_left} days")
        if r.get("meetingOverdue"):
            flags.append("meeting overdue")

        if flags:
            flagged_count += 1

        enriched.append({
            "relationshipId": str(r["relationshipId"]),
            "studentId": sid,
            "studentRef": r["studentRef"],
            "personName": r["personName"],
            "role": r["role"],
            "lastMeetingOn": r["lastMeetingOn"],
            "nextMilestone": next_milestone,
            "openFlags": flags,
        })

    # Flagged students first, then the rest — the reader lands on what matters.
    enriched.sort(key=lambda x: (len(x["openFlags"]) == 0, x["personName"]))

    return {
        "students": enriched,
        "summary": {"total": len(enriched), "flagged": flagged_count},
    }
