"""AI-P6 — Policy Compiler tables (PolicyVersion, PolicyProposal, ConfigCandidate)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class PolicyVersion(UUIDMixin, TimestampMixin, Base):
    """A registered, approved policy document version — the input to the compiler."""
    __tablename__ = "policy_version"

    policy_ref: Mapped[str] = mapped_column(String(120), index=True)
    """External code: PGR-CoP, RegSup-2024, etc."""

    version_label: Mapped[str] = mapped_column(String(60))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_version.id", ondelete="SET NULL"), nullable=True,
    )


class PolicyProposal(UUIDMixin, TimestampMixin, Base):
    """One compiler-drafted mapping proposal — the trust boundary for governance."""
    __tablename__ = "policy_proposal"

    source_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policy_version.id", ondelete="CASCADE"), index=True,
    )
    rule_candidates: Mapped[list | None] = mapped_column(JSON, nullable=True)
    """Each: {setting_key, from_value, to_value, rationale} — allow-listed only."""

    config_candidates: Mapped[list | None] = mapped_column(JSON, nullable=True)
    """Each: {config_target, changes, rationale} — allow-listed only."""

    simulation_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """Impact snapshot — affected_records, timeline_preview, workflow_preview."""

    status: Mapped[str] = mapped_column(String(20), default="draft")
    """draft | reviewed | approved | rejected | published."""

    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
