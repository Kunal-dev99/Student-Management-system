"""Admissions ORM models (arch §8.5). Portable types only (D-04)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.admissions.constants import OfferStatus


class Offer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "offer"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[OfferStatus] = mapped_column(
        Enum(OfferStatus, name="offer_status"), default=OfferStatus.draft
    )
    conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
