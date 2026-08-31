"""F3 — Recruitment depth: references, interviews, offer conditions, fee-status/visa.

Kept in a companion file so the base recruitment models stay readable; both belong to the same
module and share the Base metadata.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, ForeignKey, Index, String, Text, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class ReferenceRequestStatus(str, enum.Enum):
    requested = "requested"
    received = "received"
    declined = "declined"
    expired = "expired"


class InterviewStatus(str, enum.Enum):
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"


class InterviewOutcome(str, enum.Enum):
    unrecorded = "unrecorded"
    proceed = "proceed"
    hold = "hold"
    reject = "reject"


class FeeStatus(str, enum.Enum):
    home = "home"
    overseas = "overseas"
    channel_islands = "channel_islands"
    unknown = "unknown"


class OfferConditionStatus(str, enum.Enum):
    pending = "pending"
    satisfied = "satisfied"
    waived = "waived"


class ReferenceRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "reference_request"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    referee_name: Mapped[str] = mapped_column(String(200))
    referee_email: Mapped[str] = mapped_column(String(320))
    referee_affiliation: Mapped[str | None] = mapped_column(String(300), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[ReferenceRequestStatus] = mapped_column(
        Enum(ReferenceRequestStatus, name="reference_request_status"),
        default=ReferenceRequestStatus.requested,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_document_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Interview(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "interview"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[InterviewStatus] = mapped_column(
        Enum(InterviewStatus, name="interview_status"), default=InterviewStatus.scheduled
    )
    outcome: Mapped[InterviewOutcome] = mapped_column(
        Enum(InterviewOutcome, name="interview_outcome"), default=InterviewOutcome.unrecorded
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class InterviewPanellist(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "interview_panellist"

    interview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview.id", ondelete="CASCADE"), index=True
    )
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("person.id"), index=True)
    role: Mapped[str | None] = mapped_column(String(60), nullable=True)  # "chair", "assessor"

    __table_args__ = (
        Index("uq_interview_panellist", "interview_id", "person_id", unique=True),
    )


class OfferCondition(UUIDMixin, TimestampMixin, Base):
    """First-class offer condition — replaces the free-form ``conditions`` JSON on Offer.

    ``conditions`` on Offer stays for backward compatibility; new conditions live here and are the
    ones the accept-offer gate checks against.
    """
    __tablename__ = "offer_condition"

    offer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("offer.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    satisfy_by: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[OfferConditionStatus] = mapped_column(
        Enum(OfferConditionStatus, name="offer_condition_status"),
        default=OfferConditionStatus.pending,
    )
    satisfied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_document_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
