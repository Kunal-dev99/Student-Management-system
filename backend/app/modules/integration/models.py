"""Integration ORM models (arch §10.3). Portable types (D-04).

integration_log records every inbound and outbound call. For inbound messages, (system,
source_id) is unique so repeats are ignored (idempotency, arch §10.2).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin
from app.modules.integration.constants import Direction, IntegrationStatus


class IntegrationLog(UUIDMixin, Base):
    __tablename__ = "integration_log"

    direction: Mapped[Direction] = mapped_column(Enum(Direction, name="integration_direction"))
    system: Mapped[str] = mapped_column(String(40), index=True)          # finance / hr / research / webhook
    event_type: Mapped[str] = mapped_column(String(80))
    aggregate_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    aggregate_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(120), nullable=True)  # inbound idempotency key
    status: Mapped[IntegrationStatus] = mapped_column(Enum(IntegrationStatus, name="integration_status"))
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("uq_integration_inbound", "system", "source_id", unique=True),)
