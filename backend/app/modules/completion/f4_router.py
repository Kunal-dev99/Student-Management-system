"""F4 — Classification workflow and certificate PDF endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.errors import NotFoundError
from app.core.storage import get_object_store
from app.db.session import get_session
from app.modules.completion.f4 import CLASSIFICATIONS, ClassificationService
from app.modules.completion.models import Award


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class ProposeBody(_Camel):
    classification: str


router = APIRouter(prefix="/students", tags=["completion"])


def _out(a: Award) -> dict:
    return {
        "studentId": str(a.student_id),
        "classification": a.classification,
        "classificationState": a.classification_state,
        "classificationTitle": CLASSIFICATIONS.get(a.classification or "", a.title),
        "proposedByUserId": str(a.proposed_by_user_id) if a.proposed_by_user_id else None,
        "confirmedByUserId": str(a.confirmed_by_user_id) if a.confirmed_by_user_id else None,
        "publishedAt": a.published_at.isoformat() if a.published_at else None,
        "certificateDocumentId": str(a.certificate_document_id) if a.certificate_document_id else None,
    }


@router.get("/{student_id}/classification", summary="Get the classification (award) state")
async def get_classification(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("student.read")),
) -> dict:
    from sqlalchemy import select

    from app.modules.student_record.router import scoped_ids

    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        raise NotFoundError("Student not found")
    a = (await session.execute(select(Award).where(Award.student_id == student_id))).scalar_one_or_none()
    if a is None:
        return {"studentId": str(student_id), "classificationState": "none", "options": sorted(CLASSIFICATIONS)}
    return {**_out(a), "options": sorted(CLASSIFICATIONS)}


@router.post("/{student_id}/classification/propose",
             summary="Chair proposes a classification (draft → proposed)")
async def propose(
    student_id: uuid.UUID,
    body: ProposeBody,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("student.write")),
) -> dict:
    a = await ClassificationService(session).propose(
        student_id, classification=body.classification, proposed_by_user_id=principal.user_id,
    )
    return _out(a)


@router.post("/{student_id}/classification/confirm",
             summary="Exam board confirms (proposed → confirmed) — approver separation enforced")
async def confirm(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("progression.decide")),
) -> dict:
    a = await ClassificationService(session).confirm(
        student_id, confirmed_by_user_id=principal.user_id,
    )
    return _out(a)


@router.post("/{student_id}/classification/publish",
             summary="Registry publishes — renders certificate PDF into the object store")
async def publish(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reports.signoff")),
) -> dict:
    a, doc = await ClassificationService(session).publish(student_id)
    body = _out(a)
    body["certificateFilename"] = doc.filename
    body["certificateSize"] = doc.size_bytes
    return body


@router.get("/{student_id}/certificate", summary="Download the certificate PDF (if published)")
async def download_certificate(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("student.read")),
):
    from sqlalchemy import select
    from app.modules.documents.models import Document
    from app.modules.student_record.router import scoped_ids

    allowed = await scoped_ids(principal, session)
    if allowed is not None and student_id not in allowed:
        raise NotFoundError("Student not found")
    a = (await session.execute(select(Award).where(Award.student_id == student_id))).scalar_one_or_none()
    if a is None or a.certificate_document_id is None:
        raise NotFoundError("No certificate — publish the classification first")
    d = (await session.execute(select(Document).where(Document.id == a.certificate_document_id))).scalar_one_or_none()
    if d is None:
        raise NotFoundError("Certificate document missing")
    payload = get_object_store().open(d.storage_key)
    return Response(
        content=payload, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{d.filename}"'},
    )
