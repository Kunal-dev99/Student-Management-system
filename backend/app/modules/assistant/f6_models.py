"""F6 — Ask PGR write intents.

The assistant is read-only in the shipped release. F6 introduces a two-step write path:
1. **propose_write** — the assistant articulates the write it would perform and stores it as
   an ``AssistantWriteIntent`` row in ``proposed`` state with a JSON preview. Nothing changes yet.
2. **execute** — the user (or an admin) confirms the intent, the platform performs the write
   inside the actor's permission scope, and the row moves to ``executed`` (or ``failed`` /
   ``cancelled``). Tier-3 blocked actions are always refused; a signed-off Tier-3 policy list
   sits in ``assistant.constants.BLOCKED_ACTIONS``.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class AssistantWriteIntent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "assistant_write_intent"

    proposed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(80), index=True)   # e.g. 'meeting.log', 'task.close'
    scope: Mapped[dict] = mapped_column(JSON)                     # inputs the write needs
    preview: Mapped[dict] = mapped_column(JSON)                   # human-readable summary
    state: Mapped[str] = mapped_column(String(20), default="proposed")   # proposed|executed|failed|cancelled
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
