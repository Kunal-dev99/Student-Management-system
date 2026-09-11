"""Institution settings storage (Phase 8 — real settings).

One row per overridden setting. A setting that has never been changed has **no row** — the
default lives in the registry (code), so a fresh install behaves identically to today and
"reset to default" is a DELETE, not a write of a copied value.
"""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class InstitutionSetting(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "institution_setting"

    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON)  # {"value": <typed value>} — JSON so bool/int/float/str all round-trip
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ValueSetOverride(UUIDMixin, TimestampMixin, Base):
    """Per-institution label / description / availability for a platform value.

    The value code itself (the shipped enum member) stays stable — code paths, migrations
    and FKs depend on it. Only its **presentation** (what admins and students see) and
    **availability** (whether it appears in new pickers) are institution-configurable.
    A value with no row here uses its shipped label and is shown everywhere.
    """
    __tablename__ = "value_set_override"
    __table_args__ = (
        UniqueConstraint("enum_name", "value_code", name="uq_value_set_override_enum_code"),
    )

    enum_name: Mapped[str] = mapped_column(String(100), index=True)
    value_code: Mapped[str] = mapped_column(String(100))
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
