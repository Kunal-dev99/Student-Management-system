"""Thesis HTTP endpoints (arch §11.5 — thesis and examination)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.student_record.router import scoped_ids
from app.modules.thesis.repository import ThesisRepository
from app.modules.thesis.schemas import (
    ExaminerNominationOut,
    IntentionRequest,
    NominateRequest,
    OutcomeRequest,
    SubmitThesisRequest,
    ThesisOut,
)
from app.modules.thesis.service import ThesisService

student_router = APIRouter(prefix="/students", tags=["thesis"])
thesis_router = APIRouter(prefix="/theses", tags=["thesis"])
nomination_router = APIRouter(prefix="/examiner-nominations", tags=["thesis"])


def _svc(session: AsyncSession) -> ThesisService:
    return ThesisService(ThesisRepository(session))


@student_router.get("/{student_id}/thesis", response_model=ThesisOut | None, summary="Get a student's thesis")
async def get_thesis(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
):
    allowed = await scoped_ids(principal, session)
    thesis = await _svc(session).get_for_student(student_id, allowed_ids=allowed)
    return ThesisOut.model_validate(thesis) if thesis else None


@student_router.post("/{student_id}/thesis/intention", response_model=ThesisOut, status_code=201, summary="Declare intention to submit")
async def declare_intention(
    student_id: uuid.UUID,
    body: IntentionRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> ThesisOut:
    return ThesisOut.model_validate(await _svc(session).declare_intention(student_id, body.title))


@thesis_router.post("/{thesis_id}/submit", response_model=ThesisOut, summary="Submit the thesis")
async def submit_thesis(
    thesis_id: uuid.UUID,
    body: SubmitThesisRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> ThesisOut:
    return ThesisOut.model_validate(await _svc(session).submit(thesis_id, body.title, body.document_ref))


@thesis_router.get("/{thesis_id}/examiners", response_model=list[ExaminerNominationOut], summary="List examiner nominations")
async def list_examiners(
    thesis_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.read")),
) -> list[ExaminerNominationOut]:
    rows = await _svc(session).examiners_for_thesis(thesis_id)
    return [ExaminerNominationOut.model_validate(r) for r in rows]


@thesis_router.post("/{thesis_id}/examiners", response_model=ExaminerNominationOut, status_code=201, summary="Nominate an examiner")
async def nominate_examiner(
    thesis_id: uuid.UUID,
    body: NominateRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> ExaminerNominationOut:
    nomination = await _svc(session).nominate_examiner(thesis_id, body.examiner_person_id, body.examiner_type)
    rows = await _svc(session).examiners_for_thesis(thesis_id)
    return ExaminerNominationOut.model_validate(next(r for r in rows if r["id"] == nomination.id))


@nomination_router.post("/{nomination_id}/approve", response_model=ExaminerNominationOut, summary="Approve examiner nomination")
async def approve_nomination(
    nomination_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.write")),
) -> ExaminerNominationOut:
    nomination = await _svc(session).approve_nomination(nomination_id, principal.user_id)
    rows = await _svc(session).examiners_for_thesis(nomination.thesis_id)
    return ExaminerNominationOut.model_validate(next(r for r in rows if r["id"] == nomination.id))


@thesis_router.post("/{thesis_id}/examination/outcome", response_model=ThesisOut, summary="Record examination outcome")
async def record_outcome(
    thesis_id: uuid.UUID,
    body: OutcomeRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("student.write")),
) -> ThesisOut:
    return ThesisOut.model_validate(await _svc(session).record_outcome(thesis_id, body.outcome, body.viva_date))
