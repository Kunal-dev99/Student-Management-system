"""Institution settings storage (Phase 8 — real settings).

One row per overridden setting. A setting that has never been changed has **no row** — the
default lives in the registry (code), so a fresh install behaves identically to today and
"reset to default" is a DELETE, not a write of a copied value.
"""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class InstitutionSetting(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "institution_setting"

    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON)  # {"value": <typed value>} — JSON so bool/int/float/str all round-trip
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
