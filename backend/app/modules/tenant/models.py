"""Tenant model — Phase 1 multi-tenant skeleton.

A tenant is one customer institution. The seed migration creates a "default" tenant
that every existing row is backfilled to; that lets the platform keep running as a
single-tenant deployment until Phase 2 spreads `tenant_id` across the domain.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class Tenant(UUIDMixin, TimestampMixin, Base):
    """One customer institution. Subdomain routes web traffic; branding is optional JSON."""
    __tablename__ = "tenant"

    name: Mapped[str] = mapped_column(String(200))
    subdomain: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    branding: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    @property
    def is_active(self) -> bool:
        return self.activated_at is not None and self.deactivated_at is None
