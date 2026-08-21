"""Audit log (arch §17) — an append-only record of who did what, when.

Populated automatically by AuditMiddleware for every state-changing request, and by explicit
service-layer calls for domain events that need richer before/after detail. Portable types (D-04).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class AuditLog(UUIDMixin, Base):
    __tablename__ = "audit_log"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True)   # e.g. "POST /api/v1/students/{id}"
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )
