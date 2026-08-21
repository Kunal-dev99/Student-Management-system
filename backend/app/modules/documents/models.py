"""Document metadata (arch §13.3). Bytes live in the object store; this row is the index.

`owner_type` + `owner_id` attach a document to any aggregate (student, thesis, application,
milestone, ...). `scan_status` is a hook for a future AV/similarity scan; defaults to clean.
Portable types (D-04).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class Document(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "document"

    owner_type: Mapped[str] = mapped_column(String(50), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    doc_type: Mapped[str | None] = mapped_column(String(60), nullable=True)  # e.g. thesis, reference, review
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(120))
    scan_status: Mapped[str] = mapped_column(String(20), default="clean")
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    __table_args__ = (Index("ix_document_owner", "owner_type", "owner_id"),)
