"""AI-P4 — Versioned document extraction + Research Change Radar findings."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class DocumentVersion(UUIDMixin, TimestampMixin, Base):
    """Immutable version of a document (from the object store), with extraction metadata."""
    __tablename__ = "document_version"

    document_ref: Mapped[str] = mapped_column(String(300), index=True)
    """The domain reference for the document — proposal ref, thesis ref, etc."""

    student_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    object_key: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    extraction_status: Mapped[str] = mapped_column(String(20), default="pending")
    """pending | extracted | failed."""
    extractor_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DocumentChunk(UUIDMixin, TimestampMixin, Base):
    """One extracted passage with a stable locator for evidence pointers."""
    __tablename__ = "document_chunk"

    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_version.id", ondelete="CASCADE"), index=True,
    )
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_heading: Mapped[str | None] = mapped_column(String(300), nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_hash: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(String(8000))


class ChangeFinding(UUIDMixin, TimestampMixin, Base):
    """One detected material change between two document versions.

    NEVER an ethics decision — the "for_review" suffix in ethics_relevant_change_for_review
    is a flag, not a finding of non-compliance.
    """
    __tablename__ = "change_finding"

    version_a_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_version.id", ondelete="CASCADE"), index=True,
    )
    version_b_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_version.id", ondelete="CASCADE"), index=True,
    )
    change_type: Mapped[str] = mapped_column(String(60), index=True)
    """objective_added | objective_removed | objective_modified | method_changed |
       population_changed | sample_size_changed | scope_changed | timeline_changed |
       limitation_added | ethics_relevant_change_for_review."""

    severity_for_review: Mapped[str] = mapped_column(String(20), default="info")
    """info | notice | urgent — reviewer priority hint."""

    source_a_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_b_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str] = mapped_column(String(1000))
    reviewer_disposition: Mapped[str | None] = mapped_column(String(20), nullable=True)
    """accepted | dismissed | noted — set when a reviewer acts on the finding."""
    reviewer_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
