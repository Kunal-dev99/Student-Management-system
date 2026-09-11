"""Audit for every composition attempt.

One row per request, written whether it succeeded or not. It backs three things: the
per-user daily budget (see `core/llm/governance.check_budget`), the "why did it show me
that?" disclosure in the UI, and the answer to an auditor asking what was sent to a
third-party model on behalf of which student.

`question` is stored redacted. Nothing in this table should identify a person.
"""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class ComposerRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "composer_run"

    # MT-1 — nullable while the tenant column is still spreading across the domain.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # Redacted before write — see governance.redact.
    question: Mapped[str] = mapped_column(Text)
    # Named composition template when one was used, else null for a free-form ask.
    composition_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    # Data functions the model asked for, in call order.
    functions_called: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # The validated spec that was rendered. Null on failure.
    composition: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    # Populated on failure: validation errors, provider errors, gate refusals.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
