"""Supervision HTTP endpoints (arch §11.5 — supervision)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.student_record.router import scoped_ids
from app.modules.supervision.repository import SupervisionRepository
from app.modules.supervision.schemas import (
    AssignRequest,
    CaseloadItem,
    EndRequest,
    MeetingOut,
    MeetingRequest,
    SupervisorOut,
)
from app.modules.supervision.service import SupervisionService

student_scoped = APIRouter(prefix="/students", tags=["supervision"])
sup_router = APIRouter(prefix="/supervisors", tags=["supervision"])


def _svc(session: AsyncSession) -> SupervisionService:
    return SupervisionService(SupervisionRepository(session))


@student_scoped.get("/{student_id}/supervisors", response_model=list[SupervisorOut], summary="Supervisors for a student")
async def list_supervisors(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> list[SupervisorOut]:
    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        return []
    rows = await _svc(session).supervisors_for_student(student_id)
    return [SupervisorOut.model_validate(r) for r in rows]


@student_scoped.post("/{student_id}/supervisors", response_model=SupervisorOut, status_code=201, summary="Assign supervisor")
async def assign_supervisor(
    student_id: uuid.UUID,
    body: AssignRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> SupervisorOut:
    rel = await _svc(session).assign(
        student_id, body.supervisor_person_id, body.role, weighting_pct=body.weighting_pct
    )
    rows = await _svc(session).supervisors_for_student(student_id)
    match = next(r for r in rows if r["id"] == rel.id)
    return SupervisorOut.model_validate(match)


@sup_router.post("/{rel_id}/end", response_model=SupervisorOut, summary="End a supervision relationship")
async def end_supervision(
    rel_id: uuid.UUID,
    body: EndRequest | None = None,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> SupervisorOut:
    rel = await _svc(session).end(rel_id, body.reason if body else None)
    rows = await _svc(session).supervisors_for_student(rel.student_id)
    match = next(r for r in rows if r["id"] == rel.id)
    return SupervisorOut.model_validate(match)


@sup_router.get("/{person_id}/capacity", summary="Supervisor capacity (current vs max supervisees)")
async def capacity(
    person_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.read")),
) -> dict:
    return await _svc(session).capacity_for(person_id)


# --- Phase 4B.5 — supervision meeting log (row-scoped like the student record) ---

@student_scoped.get("/{student_id}/supervision-meetings", response_model=list[MeetingOut], summary="Supervision meeting log")
async def list_meetings(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> list[MeetingOut]:
    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        return []
    rows = await _svc(session).meetings_for_student(student_id)
    return [MeetingOut.model_validate(r) for r in rows]


@student_scoped.post("/{student_id}/supervision-meetings", response_model=MeetingOut, status_code=201, summary="Record a supervision meeting")
async def record_meeting(
    student_id: uuid.UUID,
    body: MeetingRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> MeetingOut:
    # Supervisors (read-only on student.write) must be able to log their own meetings, so this
    # is guarded by student.read + row scope rather than student.write.
    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        from app.core.errors import PermissionError as AppPermissionError

        raise AppPermissionError("Student is out of your scope")
    row = await _svc(session).record_meeting(
        student_id, supervisor_person_id=body.supervisor_person_id, met_on=body.met_on,
        format=body.format, duration_minutes=body.duration_minutes, notes=body.notes,
        actions=body.actions, next_meeting_on=body.next_meeting_on,
        recorded_by_user_id=principal.user_id,
    )
    return MeetingOut.model_validate(row)


@student_scoped.get("/{student_id}/supervision-compliance", summary="Is the supervision record up to date?")
async def meeting_compliance(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> dict:
    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        from app.core.errors import NotFoundError

        raise NotFoundError("Student not found")
    return await _svc(session).meeting_compliance(student_id)


@sup_router.post("/meetings/{meeting_id}/confirm", response_model=MeetingOut, summary="Student confirms a meeting record")
async def confirm_meeting(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.read")),
) -> MeetingOut:
    return MeetingOut.model_validate(await _svc(session).confirm_meeting(meeting_id))


@sup_router.get("/{person_id}/students", response_model=list[CaseloadItem], summary="Supervisor caseload")
async def caseload(
    person_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.read")),
) -> list[CaseloadItem]:
    rows = await _svc(session).caseload(person_id)
    return [CaseloadItem.model_validate(r) for r in rows]
