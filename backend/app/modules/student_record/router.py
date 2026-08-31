"""Student record HTTP endpoints (arch §11.5 — student record).

Reads are row-scoped from the principal (arch §12.3): a supervisor sees only students they
currently supervise; broad roles see all.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import student_scope
from app.core.dependencies import get_current_principal, require_permission
from app.core.pagination import PageParams, list_envelope, page_params
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.student_record.repository import StudentRepository
from app.modules.student_record.lifecycle import LifecycleService
from app.modules.student_record.schemas import (
    LifecycleDecision,
    LifecycleEventOut,
    LifecycleEventRequest,
    ResearchProjectOut,
    ReturnRequest,
    StudentOut,
    StudentSummary,
    StudentUpdate,
)
from app.modules.student_record.service import StudentService

router = APIRouter(prefix="/students", tags=["student"])
programmes_router = APIRouter(prefix="/programmes", tags=["student"])
lifecycle_router = APIRouter(prefix="/lifecycle-events", tags=["student"])


def _svc(session: AsyncSession) -> StudentService:
    return StudentService(StudentRepository(session))


@programmes_router.get("", summary="List programmes")
async def list_programmes(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.read")),
) -> list[dict]:
    rows = await StudentRepository(session).list_programmes()
    return [{"id": str(p.id), "name": p.name, "code": p.code} for p in rows]


async def scoped_ids(principal: Principal, session: AsyncSession) -> list[uuid.UUID] | None:
    """Resolve the student ids this principal may see (None = unrestricted)."""
    scope = student_scope(principal)
    if scope.kind == "all":
        return None
    if scope.kind == "supervisor" and scope.person_id is not None:
        from app.modules.supervision.repository import SupervisionRepository
        from app.modules.supervision.service import SupervisionService

        return await SupervisionService(
            SupervisionRepository(session)
        ).supervised_student_ids(scope.person_id)
    if scope.kind == "self" and scope.person_id is not None:
        student = await StudentRepository(session).get_by_person(scope.person_id)
        return [student.id] if student else []
    return []  # no scope -> sees nothing


@router.get("", summary="List students (row-scoped)")
async def list_students(
    page: PageParams = Depends(page_params),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> dict:
    allowed = await scoped_ids(principal, session)
    rows, total = await _svc(session).list_students(limit=page.limit, offset=page.offset, allowed_ids=allowed)
    # One batch lookup for the page's person names — the register is read by
    # humans, and humans find students by name, not by reference.
    from sqlalchemy import select

    from app.modules.person.models import Person

    person_ids = {s.person_id for s in rows}
    names: dict = {}
    if person_ids:
        people = (await session.execute(select(Person).where(Person.id.in_(person_ids)))).scalars()
        names = {p.id: f"{p.given_name} {p.family_name}" for p in people}
    data = [
        {**StudentOut.model_validate(s).model_dump(by_alias=True),
         "personName": names.get(s.person_id)}
        for s in rows
    ]
    return list_envelope(data, limit=page.limit, total=total)


@router.get("/{student_id}", response_model=StudentOut, summary="Get a student (row-scoped)")
async def get_student(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> StudentOut:
    allowed = await scoped_ids(principal, session)
    return StudentOut.model_validate(await _svc(session).get_student(student_id, allowed_ids=allowed))


@router.patch("/{student_id}", response_model=StudentOut, summary="Update a student")
async def update_student(
    student_id: uuid.UUID,
    body: StudentUpdate,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> StudentOut:
    student = await _svc(session).update_student(student_id, body.model_dump(exclude_unset=True))
    return StudentOut.model_validate(student)


@router.get("/{student_id}/project", response_model=ResearchProjectOut | None, summary="Research project")
async def get_project(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
):
    allowed = await scoped_ids(principal, session)
    student = await _svc(session).get_student(student_id, allowed_ids=allowed)
    return ResearchProjectOut.model_validate(student.project) if student.project else None


@router.get("/{student_id}/summary", response_model=StudentSummary, summary="Journey summary")
async def get_summary(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> StudentSummary:
    allowed = await scoped_ids(principal, session)
    return StudentSummary.model_validate(await _svc(session).summary(student_id, allowed_ids=allowed))


# --- Phase 6.5 — PGR exception lifecycle (suspension / extension / mode change) ---

@router.get("/{student_id}/lifecycle-events", response_model=list[LifecycleEventOut],
            summary="Suspensions, extensions and mode changes")
async def list_lifecycle_events(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> list[LifecycleEventOut]:
    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        return []
    svc = LifecycleService(session)
    return [LifecycleEventOut.model_validate(svc.out(e)) for e in await svc.events_for_student(student_id)]


@router.post("/{student_id}/lifecycle-events", response_model=LifecycleEventOut, status_code=201,
             summary="Request a suspension, extension or mode change")
async def request_lifecycle_event(
    student_id: uuid.UUID,
    body: LifecycleEventRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.write")),
) -> LifecycleEventOut:
    svc = LifecycleService(session)
    event = await svc.request_event(
        student_id, event_type=body.event_type, reason=body.reason,
        start_date=body.start_date, end_date=body.end_date,
        extension_days=body.extension_days, new_mode=body.new_mode,
        requested_by_user_id=principal.user_id,
    )
    return LifecycleEventOut.model_validate(svc.out(event))


@router.post("/{student_id}/return", summary="Record a return from suspension")
async def record_return(
    student_id: uuid.UUID,
    body: ReturnRequest | None = None,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> dict:
    return await LifecycleService(session).record_return(
        student_id, returned_on=body.returned_on if body else None
    )


@lifecycle_router.post("/{event_id}/approve", summary="Approve — this is what moves the dates")
async def approve_lifecycle_event(
    event_id: uuid.UUID,
    body: LifecycleDecision | None = None,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.lifecycle.approve")),
) -> dict:
    return await LifecycleService(session).approve_event(
        event_id, approver_user_id=principal.user_id, note=body.note if body else None
    )


@lifecycle_router.post("/{event_id}/reject", summary="Reject a lifecycle request")
async def reject_lifecycle_event(
    event_id: uuid.UUID,
    body: LifecycleDecision | None = None,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.lifecycle.approve")),
) -> dict:
    return await LifecycleService(session).reject_event(
        event_id, approver_user_id=principal.user_id, note=body.note if body else None
    )
