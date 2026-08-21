"""Supervision ORM model (arch §8.7).

History is preserved: a supervisor change ends one row (valid_to) and opens another rather
than editing in place. Portable types only (D-04).
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.supervision.constants import SupervisionStatus, SupervisorRole


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
