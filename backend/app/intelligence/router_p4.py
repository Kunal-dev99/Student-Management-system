"""AI-P4 endpoints — versioned documents + Research Change Radar."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_read_session, get_session
from app.intelligence.documents import ChangeRadar, DocumentPipeline
from app.intelligence.models_p4 import ChangeFinding, DocumentVersion

router_p4 = APIRouter(prefix="/intelligence", tags=["intelligence"])


class DocumentVersionIn(BaseModel):
    document_ref: str
    object_key: str
    content: str
    student_id: uuid.UUID | None = None
    mime_type: str | None = None


class DocumentVersionOut(BaseModel):
    id: uuid.UUID
    document_ref: str
    content_hash: str
    extraction_status: str
    extractor_version: str | None = None
    page_count: int | None = None


class ChangeFindingOut(BaseModel):
    id: uuid.UUID
    change_type: str
    severity_for_review: str
    summary: str
    source_a_ref: dict[str, Any] | None = None
    source_b_ref: dict[str, Any] | None = None
    reviewer_disposition: str | None = None


class DispositionIn(BaseModel):
    disposition: str
    note: str | None = None


@router_p4.post("/documents/versions", response_model=DocumentVersionOut, status_code=201,
                 summary="Register a new document version and extract chunks (deterministic)")
async def add_version(
    body: DocumentVersionIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("document.read")),
) -> DocumentVersionOut:
    v = await DocumentPipeline(session).register_version(
        document_ref=body.document_ref,
        object_key=body.object_key,
        content=body.content,
        student_id=body.student_id,
        mime_type=body.mime_type,
        uploaded_by_user_id=principal.user_id,
    )
    await session.commit()
    return DocumentVersionOut(id=v.id, document_ref=v.document_ref,
                               content_hash=v.content_hash,
                               extraction_status=v.extraction_status,
                               extractor_version=v.extractor_version,
                               page_count=v.page_count)


@router_p4.post("/documents/compare", response_model=list[ChangeFindingOut],
                 summary="Compare two document versions (Research Change Radar)")
async def compare(
    version_a: uuid.UUID, version_b: uuid.UUID,
    include_semantic: bool = False,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_permission("document.read")),
) -> list[ChangeFindingOut]:
    findings = await ChangeRadar(session).compare(
        version_a, version_b, include_semantic=include_semantic,
    )
    await session.commit()
    return [ChangeFindingOut(id=f.id, change_type=f.change_type,
                              severity_for_review=f.severity_for_review,
                              summary=f.summary,
                              source_a_ref=f.source_a_ref,
                              source_b_ref=f.source_b_ref,
                              reviewer_disposition=f.reviewer_disposition)
             for f in findings]


@router_p4.get("/documents/{document_ref}/versions",
                response_model=list[DocumentVersionOut],
                summary="Every version registered for one document reference")
async def list_versions(
    document_ref: str,
    session: AsyncSession = Depends(get_read_session),
    _: Principal = Depends(require_permission("document.read")),
) -> list[DocumentVersionOut]:
    rows = (await session.execute(
        select(DocumentVersion).where(DocumentVersion.document_ref == document_ref)
        .order_by(DocumentVersion.uploaded_at.asc())
    )).scalars().all()
    return [DocumentVersionOut(id=v.id, document_ref=v.document_ref,
                                content_hash=v.content_hash,
                                extraction_status=v.extraction_status,
                                extractor_version=v.extractor_version,
                                page_count=v.page_count) for v in rows]


@router_p4.post("/findings/{finding_id}/disposition",
                 summary="Reviewer disposes a Change Radar finding")
async def dispose_finding(
    finding_id: uuid.UUID,
    body: DispositionIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("document.read")),
) -> dict[str, Any]:
    row = await session.get(ChangeFinding, finding_id)
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Finding not found")
    row.reviewer_disposition = body.disposition
    row.reviewer_note = body.note
    row.reviewed_by_user_id = principal.user_id
    from datetime import datetime, timezone
    row.reviewed_at = datetime.now(timezone.utc)
    await session.commit()
    return {"id": str(row.id), "disposition": row.reviewer_disposition}
