"""Document business rules (arch §13.3): store bytes in the object store, index metadata in the DB."""
from __future__ import annotations

import os
import uuid

from app.core.errors import NotFoundError
from app.core.storage import get_object_store
from app.modules.documents.models import Document
from app.modules.documents.repository import DocumentRepository


class DocumentService:
    def __init__(self, repo: DocumentRepository) -> None:
        self.repo = repo
        self.store = get_object_store()

    async def list_for_owner(self, owner_type: str, owner_id: uuid.UUID) -> list[Document]:
        return await self.repo.list_for_owner(owner_type, owner_id)

    async def create(
        self, *, owner_type: str, owner_id: uuid.UUID, doc_type: str | None,
        filename: str, content_type: str, data: bytes, uploaded_by: uuid.UUID | None,
    ) -> Document:
        suffix = os.path.splitext(filename)[1][:12]  # keep a short extension for downloads
        key, checksum, size = self.store.save(data, suffix=suffix)
        doc = Document(
            owner_type=owner_type, owner_id=owner_id, doc_type=doc_type,
            filename=filename, content_type=content_type or "application/octet-stream",
            size_bytes=size, checksum_sha256=checksum, storage_key=key,
            scan_status="clean", uploaded_by=uploaded_by,
        )
        self.repo.add(doc)
        await self.repo.session.commit()
        await self.repo.session.refresh(doc)
        return doc

    async def get(self, doc_id: uuid.UUID) -> Document:
        doc = await self.repo.get(doc_id)
        if doc is None:
            raise NotFoundError("Document not found")
        return doc

    def read_bytes(self, doc: Document) -> bytes:
        return self.store.open(doc.storage_key)

    async def delete(self, doc_id: uuid.UUID) -> None:
        doc = await self.get(doc_id)
        self.store.delete(doc.storage_key)
        await self.repo.session.delete(doc)
        await self.repo.session.commit()
