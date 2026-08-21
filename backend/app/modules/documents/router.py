"""Document upload / download / list / delete (arch §13.3).

Bytes go to the object store; metadata to the `document` table. Student-owned documents are
row-scoped: a supervisor or student only sees documents for students in their scope.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_current_principal, require_permission
from app.core.errors import PermissionError, ValidationAppError
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.documents.models import Document
from app.modules.documents.repository import DocumentRepository
from app.modules.documents.service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


def _out(d: Document) -> dict:
    return {
        "id": str(d.id),
        "ownerType": d.owner_type,
        "ownerId": str(d.owner_id),
        "docType": d.doc_type,
        "filename": d.filename,
        "contentType": d.content_type,
        "sizeBytes": d.size_bytes,
        "scanStatus": d.scan_status,
        "uploadedBy": str(d.uploaded_by) if d.uploaded_by else None,
        "createdAt": d.created_at.isoformat() if d.created_at else None,
    }


async def _enforce_student_scope(
    owner_type: str, owner_id: uuid.UUID, principal: Principal, session: AsyncSession
) -> None:
    """When a document hangs off a student, apply the same row-scoping as the student record."""
    if owner_type != "student":
        return
    from app.modules.student_record.router import scoped_ids

    allowed = await scoped_ids(principal, session)
    if allowed is not None and owner_id not in allowed:
        raise PermissionError("Document owner is out of your scope")


@router.get("", summary="List documents for an owner (row-scoped)")
async def list_documents(
    ownerType: str,
    ownerId: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("document.read")),
) -> list[dict]:
    await _enforce_student_scope(ownerType, ownerId, principal, session)
    svc = DocumentService(DocumentRepository(session))
    return [_out(d) for d in await svc.list_for_owner(ownerType, ownerId)]


@router.post("", status_code=201, summary="Upload a document")
async def upload_document(
    ownerType: str = Form(...),
    ownerId: uuid.UUID = Form(...),
    docType: str | None = Form(None),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("document.write")),
) -> dict:
    await _enforce_student_scope(ownerType, ownerId, principal, session)
    data = await file.read()
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    if len(data) == 0:
        raise ValidationAppError("Empty file")
    if len(data) > max_bytes:
        raise ValidationAppError(f"File exceeds {get_settings().max_upload_mb} MB limit")
    svc = DocumentService(DocumentRepository(session))
    doc = await svc.create(
        owner_type=ownerType, owner_id=ownerId, doc_type=docType,
        filename=file.filename or "upload", content_type=file.content_type or "application/octet-stream",
        data=data, uploaded_by=principal.user_id,
    )
    return _out(doc)


@router.get("/{doc_id}/download", summary="Download a document (row-scoped)")
async def download_document(
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("document.read")),
) -> Response:
    svc = DocumentService(DocumentRepository(session))
    doc = await svc.get(doc_id)
    await _enforce_student_scope(doc.owner_type, doc.owner_id, principal, session)
    data = svc.read_bytes(doc)
    return Response(
        content=data,
        media_type=doc.content_type,
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )


@router.delete("/{doc_id}", status_code=204, summary="Delete a document")
async def delete_document(
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("document.write")),
) -> Response:
    svc = DocumentService(DocumentRepository(session))
    doc = await svc.get(doc_id)
    await _enforce_student_scope(doc.owner_type, doc.owner_id, principal, session)
    await svc.delete(doc_id)
    return Response(status_code=204)
