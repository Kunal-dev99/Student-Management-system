"""Supervision HTTP endpoints (arch §11.5 — supervision)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_session
from app.modules.supervision.repository import SupervisionRepository
from app.modules.supervision.schemas import (
    AssignRequest,
    CaseloadItem,
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
    _=Depends(require_permission("student.read")),
) -> list[SupervisorOut]:
    rows = await _svc(session).supervisors_for_student(student_id)
    return [SupervisorOut.model_validate(r) for r in rows]


@student_scoped.post("/{student_id}/supervisors", response_model=SupervisorOut, status_code=201, summary="Assign supervisor")
async def assign_supervisor(
    student_id: uuid.UUID,
    body: AssignRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> SupervisorOut:
    rel = await _svc(session).assign(student_id, body.supervisor_person_id, body.role)
    rows = await _svc(session).supervisors_for_student(student_id)
    match = next(r for r in rows if r["id"] == rel.id)
    return SupervisorOut.model_validate(match)


@sup_router.post("/{rel_id}/end", response_model=SupervisorOut, summary="End a supervision relationship")
async def end_supervision(
    rel_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> SupervisorOut:
    rel = await _svc(session).end(rel_id)
    rows = await _svc(session).supervisors_for_student(rel.student_id)
    match = next(r for r in rows if r["id"] == rel.id)
    return SupervisorOut.model_validate(match)


@sup_router.get("/{person_id}/students", response_model=list[CaseloadItem], summary="Supervisor caseload")
async def caseload(
    person_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.read")),
) -> list[CaseloadItem]:
    rows = await _svc(session).caseload(person_id)
    return [CaseloadItem.model_validate(r) for r in rows]
