"""W2 endpoints — SupervisorProfile + assignment-request workflow."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_read_session, get_session
from app.modules.research.matching import MatchingService
from app.modules.supervision.constants import SupervisorRole
from app.modules.supervision.w2_models import (
    AssignmentRequestState, SupervisorAvailability,
)
from app.modules.supervision.w2_service import (
    SupervisorAssignmentService, SupervisorProfileService,
)


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# ---------------------------- Profile schemas

class ProfileIn(_Camel):
    max_students: int | None = None
    availability: SupervisorAvailability | None = None
    accepting_new: bool | None = None
    sabbatical_from: date | None = None
    sabbatical_to: date | None = None
    bio: str | None = None
    research_area_ids: list[uuid.UUID] | None = None


class RequestIn(_Camel):
    supervisor_person_id: uuid.UUID
    role: SupervisorRole = SupervisorRole.primary
    match_score: int | None = None
    match_reasons: list[dict] | None = None
    note: str | None = None


class RejectIn(_Camel):
    reason: str


sup_profile_router = APIRouter(prefix="/supervisors", tags=["supervision"])
sup_requests_router = APIRouter(prefix="/supervisor-requests", tags=["supervision"])
sup_student_router = APIRouter(prefix="/students", tags=["supervision"])


# ---------------------------- Profile endpoints

@sup_profile_router.get("/{person_id}/profile",
                        summary="W2 — supervisor profile (null when none set)")
async def get_profile(
    person_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("student.read")),
) -> dict:
    return {"profile": await SupervisorProfileService(session).get_or_none(person_id)}


@sup_profile_router.put("/{person_id}/profile",
                        summary="W2 — create or update the supervisor profile (admin.configure)")
async def upsert_profile(
    person_id: uuid.UUID,
    body: ProfileIn,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await SupervisorProfileService(session).upsert(
        person_id,
        max_students=body.max_students,
        availability=body.availability,
        accepting_new=body.accepting_new,
        sabbatical_from=body.sabbatical_from,
        sabbatical_to=body.sabbatical_to,
        bio=body.bio,
        research_area_ids=body.research_area_ids,
    )


# ---------------------------- Recommend

@sup_profile_router.get("/recommend",
                        summary="W2 — recommend supervisors for a student (uses the matcher)")
async def recommend(
    student_id: uuid.UUID = Query(..., alias="studentId"),
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("student.read")),
) -> dict:
    """Wraps ``MatchingService.suggest_supervisors`` for the specific student's project."""
    from sqlalchemy import select
    from app.modules.student_record.models import ResearchProject, Student

    student = (await session.execute(
        select(Student).where(Student.id == student_id)
    )).scalar_one_or_none()
    if student is None:
        from app.core.errors import NotFoundError
        raise NotFoundError("Student not found")
    project = (await session.execute(
        select(ResearchProject).where(ResearchProject.student_id == student_id)
    )).scalar_one_or_none()
    matcher = MatchingService(session)
    return await matcher.suggest_supervisors(
        research_area_id=student.research_area_id if student else None,
        proposal_text=(project.research_topic if project else None),
        limit=limit,
    )


# ---------------------------- Assignment requests

@sup_student_router.post("/{student_id}/supervisor-requests", status_code=201,
                         summary="W2 — request a specific supervisor for a student")
async def create_request(
    student_id: uuid.UUID,
    body: RequestIn,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("student.write")),
) -> dict:
    row = await SupervisorAssignmentService(session).request(
        student_id=student_id,
        supervisor_person_id=body.supervisor_person_id,
        role=body.role,
        requested_by_user_id=principal.user_id,
        match_score=body.match_score,
        match_reasons=body.match_reasons,
        note=body.note,
    )
    return _request_out(row)


@sup_student_router.get("/{student_id}/supervisor-requests",
                        summary="W2 — assignment requests for one student")
async def list_for_student(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("student.read")),
) -> dict:
    rows = await SupervisorAssignmentService(session).list_for_student(student_id)
    return {"requests": [_request_out(r) for r in rows]}


@sup_requests_router.get("",
                         summary="W2 — global queue of assignment requests, filterable by state")
async def list_all(
    state: AssignmentRequestState | None = None,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("student.read")),
) -> dict:
    rows = await SupervisorAssignmentService(session).list_by_state(state)
    return {"requests": [_request_out(r) for r in rows]}


@sup_requests_router.post("/{request_id}/review",
                          summary="W2 — mark as under academic review")
async def review(
    request_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("student.write")),
) -> dict:
    row = await SupervisorAssignmentService(session).review(
        request_id, reviewed_by_user_id=principal.user_id,
    )
    return _request_out(row)


@sup_requests_router.post("/{request_id}/approve",
                          summary="W2 — approve and create the supervisor relationship")
async def approve(
    request_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("student.write")),
) -> dict:
    row, rel = await SupervisorAssignmentService(session).approve(
        request_id, decided_by_user_id=principal.user_id,
    )
    return {**_request_out(row), "relationshipId": str(rel.id)}


@sup_requests_router.post("/{request_id}/reject",
                          summary="W2 — reject with a reason")
async def reject(
    request_id: uuid.UUID,
    body: RejectIn,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("student.write")),
) -> dict:
    row = await SupervisorAssignmentService(session).reject(
        request_id, reason=body.reason, decided_by_user_id=principal.user_id,
    )
    return _request_out(row)


@sup_requests_router.post("/{request_id}/withdraw",
                          summary="W2 — withdraw an open request")
async def withdraw(
    request_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> dict:
    row = await SupervisorAssignmentService(session).withdraw(request_id)
    return _request_out(row)


def _request_out(r) -> dict:
    return {
        "id": str(r.id),
        "studentId": str(r.student_id),
        "proposedSupervisorPersonId": str(r.proposed_supervisor_person_id),
        "proposedRole": r.proposed_role.value,
        "state": r.state.value,
        "matchScore": r.match_score,
        "matchReasons": r.match_reasons,
        "requestedByUserId": str(r.requested_by_user_id) if r.requested_by_user_id else None,
        "reviewedByUserId": str(r.reviewed_by_user_id) if r.reviewed_by_user_id else None,
        "decidedByUserId": str(r.decided_by_user_id) if r.decided_by_user_id else None,
        "rejectionReason": r.rejection_reason,
        "reviewedAt": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "decidedAt": r.decided_at.isoformat() if r.decided_at else None,
        "note": r.note,
        "createdAt": r.created_at.isoformat() if r.created_at else None,
    }
