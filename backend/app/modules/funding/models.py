"""Funding ORM models (arch §8.9).

Funding is modelled separately from student status so a student can hold several arrangements
over time. A change closes the current arrangement and opens a new one (history preserved).
Money is numeric(14,2) + a separate currency; the platform records funding relationships, not
payments. Portable types (D-04).
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.funding.constants import FundingStatus, FundingType


class FundingSource(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "funding_source"
    name: Mapped[str] = mapped_column(String(200))          # e.g. "UKRI EPSRC"
    funder_type: Mapped[str | None] = mapped_column(String(50), nullable=True)


class FundingArrangement(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "funding_arrangement"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), index=True)
    funding_type: Mapped[FundingType] = mapped_column(Enum(FundingType, name="funding_type"))
    funding_source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("funding_source.id"), nullable=True)
    stipend_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)  # null = current
    status: Mapped[FundingStatus] = mapped_column(
        Enum(FundingStatus, name="funding_status"), default=FundingStatus.planned
    )

    # Common dashboard query (arch §8.14).
    __table_args__ = (Index("ix_funding_arrangement_student_status", "student_id", "status"),)
