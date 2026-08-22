"""Funding ORM models (arch §8.9).

Funding is modelled separately from student status so a student can hold several arrangements
over time. A change closes the current arrangement and opens a new one (history preserved).
Money is numeric(14,2) + a separate currency; the platform records funding relationships, not
payments. Portable types (D-04).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.funding.constants import (
    FundingStatus,
    FundingType,
    PaymentFrequency,
    PaymentStatus,
    WaiverKind,
)


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
    # Phase 4B.7 — finance-facing detail. `cost_centre`/`project_code` let Finance reconcile
    # spend; `funder_reference` is the grant/award number the funder recognises; a percentage
    # lets several arrangements blend to fund one student.
    cost_centre: Mapped[str | None] = mapped_column(String(50), nullable=True)
    project_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    funder_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Phase 6.3 — attribute the money to the award that pays for it, completing the lineage.
    research_award_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_award.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contribution_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_frequency: Mapped[PaymentFrequency | None] = mapped_column(
        Enum(PaymentFrequency, name="payment_frequency"), nullable=True
    )

    # Common dashboard query (arch §8.14).
    __table_args__ = (Index("ix_funding_arrangement_student_status", "student_id", "status"),)


class StipendPayment(UUIDMixin, TimestampMixin, Base):
    """One instalment of a stipend (arch §8.9, §10.1).

    The platform schedules and tracks instalments; Finance remains the system of record for the
    actual disbursement, so a `finance_reference` links the two.
    """
    __tablename__ = "stipend_payment"

    arrangement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("funding_arrangement.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"), default=PaymentStatus.scheduled
    )
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    finance_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_stipend_payment_arrangement_status", "arrangement_id", "status"),)


class FeeWaiver(UUIDMixin, TimestampMixin, Base):
    """A tuition/bench fee waiver attached to a student (arch §8.9)."""
    __tablename__ = "fee_waiver"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student.id", ondelete="CASCADE"), index=True)
    arrangement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("funding_arrangement.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[WaiverKind] = mapped_column(Enum(WaiverKind, name="waiver_kind"))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    academic_year: Mapped[str | None] = mapped_column(String(9), nullable=True)  # e.g. "2026/27"
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
