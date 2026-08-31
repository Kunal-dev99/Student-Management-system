"""Progression ORM models (arch §8.8).

milestone_definition makes progression configurable per programme; milestone is a generated
instance for a student; progression_review records the panel decision. Portable types (D-04).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.progression.constants import (
    AppealStatus,
    MilestoneStatus,
    PanelRole,
    ProgressionOutcome,
)


class MilestoneDefinition(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "milestone_definition"

    programme_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("programme.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))                       # e.g. "Confirmation Review"
    trigger: Mapped[dict | None] = mapped_column(JSON, nullable=True)    # e.g. {"monthsAfter": "registration"}
    due_offset_days: Mapped[int] = mapped_column(Integer, default=0)     # from student start_date
    required_documents: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    review_panel: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assessment_criteria: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    possible_outcomes: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # subset of progression_outcome

    # ICR gap 1 — automatic student.registration_status flip on decide.
    # Shape: {"onDecideContinue": "PhD (upgraded)", "onDecideFail": "Withdrawn"}
    # If unset, no flip happens (default behaviour for every non-ICR milestone).
    registration_effect: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Milestone(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "milestone"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), index=True)
    milestone_definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("milestone_definition.id"), index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[MilestoneStatus] = mapped_column(
        Enum(MilestoneStatus, name="milestone_status"), default=MilestoneStatus.not_started
    )

    review: Mapped["ProgressionReview | None"] = relationship(
        back_populates="milestone", lazy="selectin", uselist=False, cascade="all, delete-orphan"
    )


class ProgressionReview(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "progression_review"

    milestone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("milestone.id", ondelete="CASCADE"), unique=True)
    student_submission_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    supervisor_assessment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    panel_decision: Mapped[ProgressionOutcome | None] = mapped_column(
        Enum(ProgressionOutcome, name="progression_outcome"), nullable=True
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Phase 4B.6 — conditions attached to a conditional outcome, the re-review date, and the
    # outcome letter issued to the student.
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    re_review_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    conditions_met_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_letter: Mapped[str | None] = mapped_column(Text, nullable=True)
    appeal_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)

    milestone: Mapped[Milestone] = relationship(back_populates="review")
    # Panel members are queried explicitly via the repository (a freshly-created review has no
    # loaded collection, and touching one here would trigger lazy IO in async context).
    panel: Mapped[list["ReviewPanelMember"]] = relationship(
        back_populates="review", lazy="raise", cascade="all, delete-orphan"
    )


class ReviewPanelMember(UUIDMixin, TimestampMixin, Base):
    """A member of a progression review panel (arch §8.8).

    A valid panel needs a chair and an assessor independent of the supervisory team; the service
    enforces that before a decision can be recorded.
    """
    __tablename__ = "review_panel_member"

    review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("progression_review.id", ondelete="CASCADE"), index=True
    )
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    role: Mapped[PanelRole] = mapped_column(Enum(PanelRole, name="panel_role"))
    is_independent: Mapped[bool] = mapped_column(Boolean, default=False)

    review: Mapped[ProgressionReview] = relationship(back_populates="panel")


class ProgressionAppeal(UUIDMixin, TimestampMixin, Base):
    """A student's appeal against a progression decision (arch §8.8)."""
    __tablename__ = "progression_appeal"

    review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("progression_review.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), index=True)
    grounds: Mapped[str] = mapped_column(Text)
    status: Mapped[AppealStatus] = mapped_column(
        Enum(AppealStatus, name="appeal_status"), default=AppealStatus.submitted
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
