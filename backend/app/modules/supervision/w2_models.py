"""W2 — SupervisorProfile + assignment-request workflow.

Two additive concerns layered on top of the existing supervision engine:

- ``SupervisorProfile`` — the first-class properties a supervisor carries (max_students,
  availability, sabbatical dates, bio, accepting_new). Where the profile is set, it wins over the
  institution-level default ``supervision.max_supervisees`` setting.

- ``SupervisorAssignmentRequest`` — a small state machine (recommended → requested → academic_review
  → approved / rejected / withdrawn) so an assignment is a decision on the record, not a silent
  insert into ``supervisor_relationship``. On ``approve`` the request creates the relationship
  atomically inside a capacity re-check (capacity might have changed since the recommendation).
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.supervision.constants import SupervisorRole as _CoreSupervisorRole


class SupervisorAvailability(str, enum.Enum):
    available = "available"
    full = "full"
    on_leave = "on_leave"


class AssignmentRequestState(str, enum.Enum):
    recommended = "recommended"     # produced by the matcher; not yet a formal request
    requested = "requested"         # a chair or PGR admin proposed a specific supervisor
    academic_review = "academic_review"
    approved = "approved"
    rejected = "rejected"
    withdrawn = "withdrawn"


# Re-export the existing supervision.SupervisorRole so the assignment-request enum matches the
# real relationship enum. Using the same values (primary / co_supervisor) means the assign step
# on approval doesn't need any translation.
SupervisorRole = _CoreSupervisorRole


class SupervisorProfile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "supervisor_profile"

    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), unique=True, index=True,
    )
    max_students: Mapped[int] = mapped_column(Integer, default=8)
    availability: Mapped[SupervisorAvailability] = mapped_column(
        Enum(SupervisorAvailability, name="supervisor_availability"),
        default=SupervisorAvailability.available, index=True,
    )
    accepting_new: Mapped[bool] = mapped_column(Boolean, default=True)
    sabbatical_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    sabbatical_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)


class SupervisorProfileArea(UUIDMixin, TimestampMixin, Base):
    """Many-to-many between supervisor profile and research_area."""
    __tablename__ = "supervisor_profile_area"

    supervisor_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("supervisor_profile.id", ondelete="CASCADE"), index=True,
    )
    research_area_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_area.id", ondelete="CASCADE"), index=True,
    )


class SupervisorAssignmentRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "supervisor_assignment_request"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True,
    )
    proposed_supervisor_person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), index=True,
    )
    proposed_role: Mapped[SupervisorRole] = mapped_column(
        # Reuse the existing 'supervisor_role' Postgres enum type so both tables share values.
        Enum(SupervisorRole, name="supervisor_role", create_type=False),
        default=SupervisorRole.primary,
    )
    state: Mapped[AssignmentRequestState] = mapped_column(
        Enum(AssignmentRequestState, name="assignment_request_state"),
        default=AssignmentRequestState.requested, index=True,
    )
    # Explanation carried forward from the matcher so a reviewer sees why this supervisor was
    # picked. Not required (a human may request a supervisor with no score at all).
    match_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_reasons: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Actor trail — every state transition attributes the person who did it.
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
