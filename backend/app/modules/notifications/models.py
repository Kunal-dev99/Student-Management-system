"""Per-user notification preferences (arch §10.4).

One row per user. `email_enabled` toggles the email channel (in-app is always on); `muted_events`
is a list of notification templates the user doesn't want emailed. Absence of a row = defaults.
"""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class NotificationPreference(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "notification_preference"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    digest: Mapped[bool] = mapped_column(Boolean, default=False)
    muted_events: Mapped[list | None] = mapped_column(JSON, default=list)
