"""Supervision ORM model (arch §8.7).

History is preserved: a supervisor change ends one row (valid_to) and opens another rather
than editing in place. Portable types only (D-04).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.supervision.constants import (
    MeetingFormat,
    SupervisionStatus,
    SupervisorRole,
)


class SupervisorRelationship(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "supervisor_relationship"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), index=True)
    supervisor_person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    role: Mapped[SupervisorRole] = mapped_column(Enum(SupervisorRole, name="supervisor_role"))
    status: Mapped[SupervisionStatus] = mapped_column(
        Enum(SupervisionStatus, name="supervision_status"), default=SupervisionStatus.assigned
    )
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)  # null = current
    # Phase 4B.5 — why a relationship ended (audit-friendly), and the weighting of a
    # co-supervisor's contribution (percentage of supervisory load).
    end_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    weighting_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SupervisionMeeting(UUIDMixin, TimestampMixin, Base):
    """A recorded supervision meeting (arch §8.7 — the supervisory record).

    Institutions must evidence regular supervision. Each meeting captures what was discussed,
    the agreed actions, and when the next meeting is due. Either party can record it; the
    student can confirm it (`student_confirmed`) so the record is jointly owned.
    """
    __tablename__ = "supervision_meeting"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), index=True)
    supervisor_person_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("person.id"), nullable=True)
    met_on: Mapped[date] = mapped_column(Date, index=True)
    format: Mapped[MeetingFormat] = mapped_column(
        Enum(MeetingFormat, name="meeting_format"), default=MeetingFormat.in_person
    )
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actions: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_meeting_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    student_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    student_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
