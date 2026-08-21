"""Document metadata data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import Document


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_owner(self, owner_type: str, owner_id: uuid.UUID) -> list[Document]:
        stmt = (
            select(Document)
            .where(Document.owner_type == owner_type, Document.owner_id == owner_id)
            .order_by(Document.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, doc_id: uuid.UUID) -> Document | None:
        return (await self.session.execute(
            select(Document).where(Document.id == doc_id)
        )).scalar_one_or_none()

    def add(self, doc: Document) -> None:
        self.session.add(doc)
