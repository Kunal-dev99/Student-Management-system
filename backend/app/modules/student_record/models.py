"""Student record + reference tables (arch §8.6).

Reference tables (department, research_area, programme) are shared read-mostly lookup data
referenced by other modules by FK — a pragmatic exception to the "no shared tables" rule for
lookups. Portable types only (D-04).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin
from app.db.history import HistoryMixin
from app.modules.student_record.constants import (
    LifecycleEventStatus,
    LifecycleEventType,
    ProgrammeType,
    StudentStatus,
    StudyMode,
)


class Department(UUIDMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "department"
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(30), unique=True)


class ResearchArea(UUIDMixin, TenantMixin, TimestampMixin, Base):
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


class Programme(UUIDMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "programme"
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(30), unique=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("department.id"), nullable=True
    )
    # ICR G1 — research (default, unchanged behaviour) vs taught (modules/assessments/award).
    programme_type: Mapped[ProgrammeType] = mapped_column(
        Enum(ProgrammeType, name="programme_type"),
        default=ProgrammeType.research,
        server_default=ProgrammeType.research.value,
    )
    # Target credit total for a taught programme (e.g. 180 for a UK MSc) — used to validate a
    # student's module load is complete before classification. NULL for research programmes.
    taught_total_credits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ICR G3 — programme admin. Expected duration drives a new student's expected end date at
    # enrolment; the supervision-meeting interval, when set, overrides the institution-wide
    # default for this programme (NULL = fall back to the global setting).
    duration_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supervision_meeting_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # ICR G1 (full taught model) — per-programme grading policy (pass mark, resit cap,
    # condonement allowance, classification thresholds). NULL = use DEFAULT_GRADING_POLICY.
    grading_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Student(UUIDMixin, TenantMixin, TimestampMixin, Base):
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

    # Effective dating, Phase 6 — optional dated facts (NULL = not recorded yet). Each caches the
    # value covering today from its history table; only the history services write them.
    fee_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    study_location: Mapped[str | None] = mapped_column(String(60), nullable=True)

    project: Mapped["ResearchProject | None"] = relationship(
        back_populates="student", lazy="selectin", uselist=False, cascade="all, delete-orphan"
    )


class StudentLifecycleEvent(UUIDMixin, TenantMixin, TimestampMixin, Base):
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
    # ICR G4 — study intensity (FTE %) for an intensity_change event: the % before and after.
    previous_intensity_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intensity_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Programme change (mid-term transfer): the programme in force before this event, the one
    # after, and the date the swap takes effect. NULL for every non-programme-change event.
    previous_programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("programme.id"), nullable=True,
    )
    new_programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("programme.id"), nullable=True,
    )
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    # Suspension leave category — medical / personal / academic / other. NULL for non-suspensions
    # and for suspensions where the category wasn't captured. Kept as a plain string (not an enum)
    # so an institution can extend the vocabulary in configuration rather than a code change; the
    # schema layer constrains the values that pass through the API today.
    leave_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Exactly how many days this event added to the expected end date (audit of the arithmetic).
    days_applied: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class StudentStatusHistory(UUIDMixin, TenantMixin, HistoryMixin, Base):
    """A student's status over time (effective dating, Phase 1; feeds HESA SessionStatus).

    Live rows (``superseded_by IS NULL``) for one student are contiguous and never overlap;
    ``student.status`` caches the value covering today. Written only by ``StatusHistoryService``.
    """
    __tablename__ = "student_status_history"
    __table_args__ = (Index("ix_student_status_history_student_from", "student_id", "valid_from"),)

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[StudentStatus] = mapped_column(Enum(StudentStatus, name="student_status"))
    # The approved lifecycle event that caused this period, when there was one.
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_lifecycle_event.id", ondelete="SET NULL"), nullable=True, index=True
    )


class StudentProgrammeHistory(UUIDMixin, TenantMixin, HistoryMixin, Base):
    """The programme a student was on over time (effective dating, Phase 2; feeds HESA
    StudentCourseSession). ``student.programme_id`` caches the programme covering today."""
    __tablename__ = "student_programme_history"
    __table_args__ = (Index("ix_student_programme_history_student_from", "student_id", "valid_from"),)

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    programme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("programme.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_lifecycle_event.id", ondelete="SET NULL"), nullable=True, index=True
    )


class StudentIntensityHistory(UUIDMixin, TenantMixin, HistoryMixin, Base):
    """Study intensity (FTE %) over time (effective dating, Phase 2; feeds HESA STULOAD).
    ``student.study_mode`` caches its summary for today (100% = full time)."""
    __tablename__ = "student_intensity_history"
    __table_args__ = (Index("ix_student_intensity_history_student_from", "student_id", "valid_from"),)

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    intensity_pct: Mapped[int] = mapped_column(Integer)
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_lifecycle_event.id", ondelete="SET NULL"), nullable=True, index=True
    )


class StudentFeeStatusHistory(UUIDMixin, TenantMixin, HistoryMixin, Base):
    """Fee status over time (effective dating, Phase 6). ``student.fee_status`` caches today's."""
    __tablename__ = "student_fee_status_history"
    __table_args__ = (Index("ix_student_fee_status_history_student_from", "student_id", "valid_from"),)

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    fee_status: Mapped[str] = mapped_column(String(30))
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_lifecycle_event.id", ondelete="SET NULL"), nullable=True, index=True
    )


class StudentLocationHistory(UUIDMixin, TenantMixin, HistoryMixin, Base):
    """Where the student studies over time (effective dating, Phase 6; HESA location of study).
    ``student.study_location`` caches today's."""
    __tablename__ = "student_location_history"
    __table_args__ = (Index("ix_student_location_history_student_from", "student_id", "valid_from"),)

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    study_location: Mapped[str] = mapped_column(String(60))
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_lifecycle_event.id", ondelete="SET NULL"), nullable=True, index=True
    )


class ResearchProject(UUIDMixin, TenantMixin, TimestampMixin, Base):
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


# --- Admin-defined custom student attributes (HESA gap capture) --------------------------------
# When a statutory return needs an attribute the core model doesn't hold, an admin defines a custom
# field (one click, no code release) and enters its value per student. Stored as definition + value
# rows (not a runtime ALTER TABLE), so it is tenant-scoped, survives migrations and can't corrupt
# the student table. Statutory mappings read these via the `custom.<key>` source path.

class StudentCustomField(UUIDMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "student_custom_field"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_custom_field_tenant_key"),)

    # Stable machine key used in the `custom.<key>` mapping path; derived from the label at create.
    key: Mapped[str] = mapped_column(String(60), index=True)
    label: Mapped[str] = mapped_column(String(120))
    # string | number | date | code — drives the entry-grid input and the picker's type badge.
    data_type: Mapped[str] = mapped_column(String(20), default="string")
    # Effective dating, Phase 6 — opt-in: keep dated history of this attribute's values (for
    # attributes a return reads as at a date). Off by default so one-off fields don't pay for it.
    track_history: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Why this attribute was created — mandatory commentary, shown in the picker and the audit trail.
    reason: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    values: Mapped[list["StudentCustomValue"]] = relationship(
        back_populates="field", cascade="all, delete-orphan", lazy="selectin"
    )


class StudentCustomValue(UUIDMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "student_custom_value"
    __table_args__ = (
        UniqueConstraint("custom_field_id", "student_id", name="uq_custom_value_field_student"),
    )

    custom_field_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_custom_field.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True
    )
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    field: Mapped[StudentCustomField] = relationship(back_populates="values")


class StudentCustomValueHistory(UUIDMixin, TenantMixin, HistoryMixin, Base):
    """Dated values of a custom attribute that keeps history (effective dating, Phase 6).
    The subject is the student's value row; ``student_custom_value.value`` caches today's."""
    __tablename__ = "student_custom_value_history"
    __table_args__ = (
        Index("ix_student_custom_value_history_value_from", "custom_value_id", "valid_from"),
    )

    custom_value_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student_custom_value.id", ondelete="CASCADE"), index=True
    )
    value: Mapped[str] = mapped_column(Text)
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_lifecycle_event.id", ondelete="SET NULL"), nullable=True
    )
