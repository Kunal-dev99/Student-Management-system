"""Export job model (arch §13.4).

An export runs as an async job on the worker tier writing to the object store. Here there is no
worker/object-store, so the job runs on request and the CSV is stored on the row; the client
polls the job then downloads. Portable types (D-04).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin
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
