"""Taught-lifecycle ORM models (ICR G1).

taught_module        — a unit of a taught programme (code, title, credits, term).
module_enrolment     — a student taking a module in a given academic year.
module_assessment    — a piece of assessment within a module (essay/exam/... + weight).
assessment_result    — a student's mark/grade for one assessment (via their enrolment).
dissertation         — the taught student's dissertation (one per student).

All portable types (D-04). Reuses ``document`` for submissions rather than storing files here.
Nothing in the research lifecycle references these tables, so a research programme never touches
them.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.taught.constants import (
    AssessmentType,
    ClassificationBand,
    ModuleEnrolmentStatus,
)


class TaughtModule(UUIDMixin, TimestampMixin, Base):
    """A unit of study on a taught programme."""
    __tablename__ = "taught_module"

    programme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programme.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    credits: Mapped[int] = mapped_column(Integer, default=0)
    term: Mapped[str | None] = mapped_column(String(60), nullable=True)  # e.g. "Autumn 2026"

    assessments: Mapped[list["ModuleAssessment"]] = relationship(
        back_populates="module", lazy="selectin", cascade="all, delete-orphan"
    )


class ModuleEnrolment(UUIDMixin, TimestampMixin, Base):
    """A student taking a module in a particular academic year."""
    __tablename__ = "module_enrolment"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("taught_module.id", ondelete="CASCADE"), index=True
    )
    academic_year: Mapped[str] = mapped_column(String(20))  # e.g. "2026/27"
    status: Mapped[ModuleEnrolmentStatus] = mapped_column(
        Enum(ModuleEnrolmentStatus, name="module_enrolment_status"),
        default=ModuleEnrolmentStatus.enrolled,
        index=True,
    )

    results: Mapped[list["AssessmentResult"]] = relationship(
        back_populates="enrolment", lazy="selectin", cascade="all, delete-orphan"
    )


class ModuleAssessment(UUIDMixin, TimestampMixin, Base):
    """A piece of assessment within a module (weights within a module should sum to 100)."""
    __tablename__ = "module_assessment"

    module_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("taught_module.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    assessment_type: Mapped[AssessmentType] = mapped_column(
        Enum(AssessmentType, name="assessment_type")
    )
    weight_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("100.00"))
    max_mark: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("100.00"))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    module: Mapped[TaughtModule] = relationship(back_populates="assessments")


class AssessmentResult(UUIDMixin, TimestampMixin, Base):
    """A student's mark for one assessment, tied to their module enrolment.

    A resit produces a second row for the same (enrolment, assessment) with ``is_resit=True`` —
    the original attempt is never overwritten, so the mark history is auditable.
    """
    __tablename__ = "assessment_result"

    module_enrolment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("module_enrolment.id", ondelete="CASCADE"), index=True
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("module_assessment.id", ondelete="CASCADE"), index=True
    )
    mark: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_resit: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    marked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    marked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    enrolment: Mapped[ModuleEnrolment] = relationship(back_populates="results")


class Dissertation(UUIDMixin, TimestampMixin, Base):
    """The taught student's dissertation — one per student, distinct from the research thesis flow."""
    __tablename__ = "dissertation"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True, unique=True
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    supervisor_person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    marked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mark: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(20), nullable=True)


class TaughtAward(UUIDMixin, TimestampMixin, Base):
    """The final classification for a taught student (credit-weighted average -> band).

    Kept as its own row (not a column on Student) so it carries its own decided-by/decided-at audit
    and mirrors how the research completion/classification flow records an award.
    """
    __tablename__ = "taught_award"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True, unique=True
    )
    final_mark: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # ``pass_`` (a Python keyword workaround) has value "pass"; store the .value, not the member
    # name, so the DB enum's 'pass' is used on both write and read.
    classification: Mapped[ClassificationBand | None] = mapped_column(
        Enum(ClassificationBand, name="classification_band",
             values_callable=lambda enum_cls: [m.value for m in enum_cls]),
        nullable=True,
    )
    credits_achieved: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
