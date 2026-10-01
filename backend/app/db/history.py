"""Effective-dated history rows (effective dating, Phase 1).

Every fact that changes over time is stored as periods rather than overwritten in place:

    valid_from   first day the value is true (inclusive)
    valid_to     first day it is no longer true (exclusive); NULL = still true

Periods are half-open, so adjacent rows share a boundary date with no gap and no overlap. A row
is never edited except to close it (set ``valid_to``). A row that was *wrong* is not deleted: it is
superseded by a corrected copy (``superseded_by``), so the record of what we believed and when
(``recorded_at``) survives. "Live" rows are the ones with ``superseded_by IS NULL``.

The current value is still cached on the owning row (e.g. ``student.status``) so screens read it
without a join; only the history service writes either.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

# Why a row exists. "initial" = first status at enrolment; "change" = reality changed on a date;
# "correction" = a fixed copy of a row that was wrong; "backfill" = rebuilt from older data.
HISTORY_ORIGINS = ("initial", "change", "correction", "backfill")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class HistoryMixin:
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="change")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    @declared_attr
    def recorded_by_user_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    @declared_attr
    def superseded_by(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(ForeignKey(f"{cls.__tablename__}.id", ondelete="SET NULL"), nullable=True)
