"""Export job model (arch §13.4).

An export runs as an async job on the worker tier writing to the object store. Here there is no
worker/object-store, so the job runs on request and the CSV is stored on the row; the client
polls the job then downloads. Portable types (D-04).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.exports.constants import ExportStatus


class ExportJob(UUIDMixin, Base):
    __tablename__ = "export_job"

    kind: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[ExportStatus] = mapped_column(Enum(ExportStatus, name="export_status"), default=ExportStatus.queued)
    filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)   # CSV (stand-in for object store)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# --- Phase 6.6 — statutory reporting as configuration (CIO vision GAP-05) ---

class ReportProfile(UUIDMixin, TimestampMixin, Base):
    """A statutory return, versioned by academic year (e.g. HESA Student 2026/27).

    Treating the return as configuration means a statutory change is a data edit, not a code
    change — and a prior year can be regenerated from the mapping that was in force then.
    """
    __tablename__ = "report_profile"

    code: Mapped[str] = mapped_column(String(40), index=True)          # e.g. HESA_STUDENT
    name: Mapped[str] = mapped_column(String(200))
    academic_year: Mapped[str] = mapped_column(String(9), index=True)  # e.g. 2026/27
    version: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (Index("uq_report_profile_version", "code", "academic_year", "version", unique=True),)


class ReportFieldMapping(UUIDMixin, TimestampMixin, Base):
    """One target field of a statutory return, and where its value comes from."""
    __tablename__ = "report_field_mapping"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("report_profile.id", ondelete="CASCADE"), index=True
    )
    target_field: Mapped[str] = mapped_column(String(80))       # the column the return expects
    position: Mapped[int] = mapped_column(Integer, default=0)   # column order in the file
    source_expression: Mapped[str] = mapped_column(String(200))  # dotted path, e.g. person.nationality
    transform: Mapped[str | None] = mapped_column(String(40), nullable=True)
    default_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_values: Mapped[list | None] = mapped_column(JSON, nullable=True)
