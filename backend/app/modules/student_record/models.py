"""Student record + reference tables (arch §8.6).

Reference tables (department, research_area, programme) are shared read-mostly lookup data
referenced by other modules by FK — a pragmatic exception to the "no shared tables" rule for
lookups. Portable types only (D-04).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.student_record.constants import (
    LifecycleEventStatus,
    LifecycleEventType,
    StudentStatus,
    StudyMode,
)


class Department(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "department"
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(30), unique=True)


class ResearchArea(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "research_area"
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(30), unique=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("department.id"), nullable=True
    )
    # W1.5 — optional self-FK for hierarchical areas ("Oncology" > "Radiobiology").
    # NULL parent = top-level. Circular references are the caller's problem — we don't ship a
    # cycle check because in every real institution the area tree is set by hand at seed time.
    parent_area_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_area.id", ondelete="SET NULL"), nullable=True, index=True,
    )


class Programme(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "programme"
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(30), unique=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("department.id"), nullable=True
    )


class Student(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "student"

    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    student_ref: Mapped[str] = mapped_column(String(40), unique=True)
    programme_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("programme.id"), nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("department.id"), nullable=True)
    research_area_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("research_area.id"), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Phase 6.5 — the date agreed at registration, kept immutable so every later adjustment is
    # auditable: expected_end_date = original_expected_end_date + sum(approved lifecycle days).
    original_expected_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    study_mode: Mapped[StudyMode] = mapped_column(
        Enum(StudyMode, name="study_mode"), default=StudyMode.full_time
    )
    status: Mapped[StudentStatus] = mapped_column(
        Enum(StudentStatus, name="student_status"), default=StudentStatus.registered
    )

    # ICR gap 1 — persisted registration string (e.g. "Provisional MPhil" → "PhD (upgraded)").
    # Flipped automatically by progression.decide when the milestone definition carries a
    # ``registration_effect`` metadata block. NULL means the platform derives the string on read
    # (backwards-compatible default; the ICR service falls back to derivation).
    registration_status: Mapped[str | None] = mapped_column(String(80), nullable=True)

    project: Mapped["ResearchProject | None"] = relationship(
        back_populates="student", lazy="selectin", uselist=False, cascade="all, delete-orphan"
    )


class StudentLifecycleEvent(UUIDMixin, TimestampMixin, Base):
    """A suspension, extension or mode change (arch §8.6; CIO vision GAP-06).

    Events are **requested then approved** — dates only move once an approver signs off, and both
    the requester and approver are recorded. The original journey is never overwritten: the
    student's `original_expected_end_date` stays put and `days_applied` records exactly what this
    event contributed, so the arithmetic can always be replayed.
    """
    __tablename__ = "student_lifecycle_event"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[LifecycleEventType] = mapped_column(
        Enum(LifecycleEventType, name="lifecycle_event_type")
    )
    status: Mapped[LifecycleEventStatus] = mapped_column(
        Enum(LifecycleEventStatus, name="lifecycle_event_status"),
        default=LifecycleEventStatus.requested, index=True,
    )
    # Suspension: the pause window. Extension: start_date is the effective date.
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)      # planned end
    actual_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # set on return
    extension_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_mode: Mapped[StudyMode | None] = mapped_column(
        Enum(StudyMode, name="study_mode"), nullable=True
    )
    new_mode: Mapped[StudyMode | None] = mapped_column(
        Enum(StudyMode, name="study_mode"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text)
    # Exactly how many days this event added to the expected end date (audit of the arithmetic).
    days_applied: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchProject(UUIDMixin, TimestampMixin, Base):
    """The student's research work — and the hinge of the funding lineage (Phase 6.3).

    Student → **ResearchProject** → ResearchAward → Funder → FundingArrangement → Stipend.
    """
    __tablename__ = "research_project"
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), index=True)
    research_topic: Mapped[str | None] = mapped_column(String(500), nullable=True)
    research_group: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Phase 6.3 — provenance: the award this work sits under, the area it belongs to, and the
    # advertised position it came from (all optional; a self-funded student has none of them).
    research_award_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_award.id", ondelete="SET NULL"), nullable=True, index=True
    )
    research_area_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_area.id"), nullable=True
    )
    research_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_opportunity.id", ondelete="SET NULL"), nullable=True
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    student: Mapped[Student] = relationship(back_populates="project")
