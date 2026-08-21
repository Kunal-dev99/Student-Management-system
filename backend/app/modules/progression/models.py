"""Progression ORM models (arch §8.8).

milestone_definition makes progression configurable per programme; milestone is a generated
instance for a student; progression_review records the panel decision. Portable types (D-04).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.progression.constants import MilestoneStatus, ProgressionOutcome


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

    milestone: Mapped[Milestone] = relationship(back_populates="review")
