"""Per-user notification preferences (arch §10.4).

One row per user. `email_enabled` toggles the email channel (in-app is always on); `muted_events`
is a list of notification templates the user doesn't want emailed. Absence of a row = defaults.

F6 — hygiene fields added: quiet hours (minutes-since-midnight local), auto-deactivation on a
hard email bounce (recorded in email_bounce).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
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
    # F6 — quiet hours in minutes since midnight (0..1439). If both set and start <= end,
    # notifications between [start, end) are suppressed (they arrive at end). If start > end,
    # the window wraps midnight. Nulls disable quiet hours.
    quiet_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quiet_end: Mapped[int | None] = mapped_column(Integer, nullable=True)


class EmailBounce(UUIDMixin, TimestampMixin, Base):
    """F6 — one row per bounce event received from the mail provider.

    A hard bounce deactivates the email channel for the affected user; a soft bounce is recorded
    but leaves the channel on.
    """
    __tablename__ = "email_bounce"

    person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    bounce_type: Mapped[str] = mapped_column(String(20))   # 'hard' | 'soft' | 'complaint'
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
