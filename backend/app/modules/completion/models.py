"""Completion and award ORM models (arch §8.11). Portable types (D-04)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.completion.constants import CompletionStatus


class Completion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "completion"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), unique=True, index=True)
    status: Mapped[CompletionStatus] = mapped_column(
        Enum(CompletionStatus, name="completion_status"), default=CompletionStatus.pending
    )
    requirements_met_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    award_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    graduation_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class Award(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "award"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    award_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    conferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
