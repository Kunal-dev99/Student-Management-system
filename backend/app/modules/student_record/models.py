"""Student record + reference tables (arch §8.6).

Reference tables (department, research_area, programme) are shared read-mostly lookup data
referenced by other modules by FK — a pragmatic exception to the "no shared tables" rule for
lookups. Portable types only (D-04).
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.student_record.constants import StudentStatus, StudyMode


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
    study_mode: Mapped[StudyMode] = mapped_column(
        Enum(StudyMode, name="study_mode"), default=StudyMode.full_time
    )
    status: Mapped[StudentStatus] = mapped_column(
        Enum(StudentStatus, name="student_status"), default=StudentStatus.registered
    )

    project: Mapped["ResearchProject | None"] = relationship(
        back_populates="student", lazy="selectin", uselist=False, cascade="all, delete-orphan"
    )


class ResearchProject(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "research_project"
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), index=True)
    research_topic: Mapped[str | None] = mapped_column(String(500), nullable=True)
    research_group: Mapped[str | None] = mapped_column(String(200), nullable=True)
    student: Mapped[Student] = relationship(back_populates="project")
