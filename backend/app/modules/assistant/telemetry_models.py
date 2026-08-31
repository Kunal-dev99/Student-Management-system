"""CB-C — Table for unmatched-query telemetry.

Every query the fuzzy router couldn't resolve confidently is logged here (with names/emails/IDs
scrubbed) so an admin can review the miss and either add a synonym or assign the phrasing to an
existing intent. The idea is very deliberately human-in-the-loop: no automation grows the
vocabulary — that keeps the intent surface reviewable and prevents adversarial drift.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class AssistantUnmatchedQuery(UUIDMixin, TimestampMixin, Base):
    """One row per query the fuzzy router flagged as unmatched or clarify."""
    __tablename__ = "assistant_unmatched_query"

    # The redacted query — never write raw user input to this column. See telemetry.py.
    query_redacted: Mapped[str] = mapped_column(Text)
    # Length of the raw query, before redaction — useful for spotting bulk-paste attacks.
    original_length: Mapped[int] = mapped_column(Integer, default=0)
    # Best-effort role hint so admins can see WHO tends to hit gaps (Student, Supervisor, ...).
    session_role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Top-N candidate intents at classification time, {name, score}.
    suggested_intents: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # When an admin has reviewed: the intent they matched this phrasing to (or NULL for "no fit").
    assigned_intent: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    # Optional note the reviewer left ("add 'chase up' as synonym to overdue_payments").
    synonym_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
