"""Thesis and examination ORM models (arch §8.10). Portable types (D-04).

Examiner nomination + management is Phase 2; the MVP covers intention → submit → examination
outcome so the completion path works.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.thesis.constants import (
    CorrectionKind,
    ExaminationOutcome,
    ExaminerType,
    ThesisStatus,
    VivaFormat,
)


class Thesis(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "thesis"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[ThesisStatus] = mapped_column(
        Enum(ThesisStatus, name="thesis_status"), default=ThesisStatus.preparation
    )
    intention_to_submit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)

    examination: Mapped["Examination | None"] = relationship(
        back_populates="thesis", lazy="selectin", uselist=False, cascade="all, delete-orphan"
    )


class ExaminerNomination(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "examiner_nomination"

    thesis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("thesis.id", ondelete="CASCADE"), index=True)
    examiner_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"))
    examiner_type: Mapped[ExaminerType] = mapped_column(Enum(ExaminerType, name="examiner_type"))
    # Phase 4B.8 — external examiners carry an affiliation, and every nomination declares whether a
    # conflict of interest exists (with a note). A declared conflict blocks approval.
    affiliation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    conflict_of_interest: Mapped[bool] = mapped_column(Boolean, default=False)
    conflict_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Examination(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "examination"

    thesis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("thesis.id", ondelete="CASCADE"), unique=True, index=True)
    viva_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Phase 4B.8 — viva scheduling detail.
    viva_location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    viva_format: Mapped[VivaFormat | None] = mapped_column(Enum(VivaFormat, name="viva_format"), nullable=True)
    viva_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[ExaminationOutcome | None] = mapped_column(
        Enum(ExaminationOutcome, name="examination_outcome"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    thesis: Mapped[Thesis] = relationship(back_populates="examination")


class ThesisCorrection(UUIDMixin, TimestampMixin, Base):
    """A corrections period opened by a pass-with-corrections / major-corrections outcome (4B.8)."""
    __tablename__ = "thesis_correction"

    thesis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("thesis.id", ondelete="CASCADE"), index=True)
    kind: Mapped[CorrectionKind] = mapped_column(Enum(CorrectionKind, name="correction_kind"))
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
