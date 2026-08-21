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
from app.modules.student_record.schemas import (
    ResearchProjectOut,
    StudentOut,
    StudentSummary,
    StudentUpdate,
)
from app.modules.student_record.service import StudentService

router = APIRouter(prefix="/students", tags=["student"])
programmes_router = APIRouter(prefix="/programmes", tags=["student"])


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
    data = [StudentOut.model_validate(s).model_dump(by_alias=True) for s in rows]
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
