"""Portal-only tables.

Kept small on purpose: student ↔ supervisor messages are their own thing, not a
generic messaging system. Threads are implicit — grouped by (student_id,
supervisor_person_id). Nothing here talks to any other module's schema; the
foreign keys are the only coupling.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class PortalMessage(UUIDMixin, TimestampMixin, Base):
    """One message between a student and one of their supervisors.

    `author_role` is either `student` or `supervisor` — it's what the reader uses to
    style the message, and it's also what the endpoint checks so a student can't send
    "as" their supervisor. The thread is implied by the (student_id, supervisor_person_id)
    pair; when we render a list of threads we group on that pair.
    """
    __tablename__ = "portal_message"

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True,
    )
    supervisor_person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), index=True,
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    author_role: Mapped[str] = mapped_column(String(20))  # 'student' | 'supervisor'
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
