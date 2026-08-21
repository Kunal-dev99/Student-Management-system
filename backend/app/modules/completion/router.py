"""Completion HTTP endpoints (arch §11.5 — completion)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.completion.repository import CompletionRepository
from app.modules.completion.schemas import CompletionOut
from app.modules.completion.service import CompletionService
from app.modules.student_record.router import scoped_ids

router = APIRouter(prefix="/students", tags=["completion"])


def _svc(session: AsyncSession) -> CompletionService:
    return CompletionService(CompletionRepository(session))


@router.get("/{student_id}/completion", response_model=CompletionOut | None, summary="Get completion")
async def get_completion(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
):
    allowed = await scoped_ids(principal, session)
    return await _svc(session).get_for_student(student_id, allowed_ids=allowed)


@router.post("/{student_id}/completion/confirm", response_model=CompletionOut, summary="Confirm completion")
async def confirm_completion(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> CompletionOut:
    return CompletionOut.model_validate(await _svc(session).confirm(student_id))


@router.post("/{student_id}/graduation", response_model=CompletionOut, summary="Graduate — sets alumni, closes funding")
async def graduate(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> CompletionOut:
    return CompletionOut.model_validate(await _svc(session).graduate(student_id))
