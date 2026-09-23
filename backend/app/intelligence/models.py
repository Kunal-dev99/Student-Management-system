"""SQLAlchemy models for the intelligence trust layer (Phase 1 foundations).

Four append-mostly tables — every row is derived data, not a source of truth. Deleting the
whole intelligence schema must leave the platform's domain data intact and its business
rules workable.

Tables:
    evidence_claim          — the trust envelope behind every AI-produced statement
    prediction_snapshot     — one row per (student, model_version, moment) probability
    driver_snapshot         — feature-level drivers captured next to each prediction
    intelligence_telemetry  — one row per app/ai call for observability + cost tracking
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class EvidenceClaim(UUIDMixin, TenantMixin, TimestampMixin, Base):
    """One factual claim attached to an AI artefact — the trust envelope.

    Every user-visible AI conclusion should carry at least one EvidenceClaim so a reader can
    click through from narrative to source (row / document passage / model version). Rows
    whose `value_hash` no longer matches the current source are flagged stale by the
    intelligence layer at read time.
    """
    __tablename__ = "evidence_claim"

    artefact_id: Mapped[uuid.UUID] = mapped_column(index=True)
    """Groups claims that back one AI response / card / plan."""

    claim_type: Mapped[str] = mapped_column(String(40), index=True)
    """deterministic_fact | model_signal | document_finding | user_context | missing_data."""

    source_type: Mapped[str] = mapped_column(String(60))
    """Domain name of the source row: student, milestone, meeting, funding_arrangement, …"""

    source_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    """Primary key of the source row (as string; sources vary in id type)."""

    locator: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """Field path for rows, or {page, section, char_start, char_end, span_hash} for docs."""

    value_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """SHA-256 of the value observed when the claim was written. Stale-detection basis."""

    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    """When the source was read — freshness signal."""

    permission_scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """The principal/roles/institution the claim was collected under (audit trail)."""

    status: Mapped[str] = mapped_column(String(30), default="verified")
    """verified | inferred_for_review | missing | superseded."""

    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """Free-form small envelope: display label, unit, dashboard link, etc."""


class PredictionSnapshot(UUIDMixin, TenantMixin, TimestampMixin, Base):
    """One mature prediction persisted alongside its model version.

    Feeds the Risk Storyline: how did this student's score move over time? Never compare
    across `model_version` where the corresponding `ModelVersionBoundary` marks the change
    as materially different (that flag lives on ml_model_version.metrics).
    """
    __tablename__ = "prediction_snapshot"
    __table_args__ = (
        UniqueConstraint("student_id", "model_version_id", "predicted_at",
                          name="uq_prediction_snapshot_student_model_time"),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), index=True,
    )
    target: Mapped[str] = mapped_column(String(80), index=True)
    """funding_continuity, progression_delay, … — the pattern-lab target key."""

    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ml_model_version.id", ondelete="CASCADE"), index=True,
    )
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    probability: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    """The operating threshold in effect at the time of scoring."""

    model_health: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """Snapshot of health signals at scoring time: PSI, matured AUC, calibration."""


class DriverSnapshot(UUIDMixin, TenantMixin, TimestampMixin, Base):
    """Feature-level driver captured next to a prediction — the "why did it move" data.

    Populated from permutation importance (baseline) or on-demand sensitivity runs. Never
    interpreted as a causal claim; the storyline treats these as *model movement drivers*,
    not real-world levers.
    """
    __tablename__ = "driver_snapshot"

    prediction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prediction_snapshot.id", ondelete="CASCADE"), index=True,
    )
    method: Mapped[str] = mapped_column(String(40))
    """permutation_importance | sensitivity_run | shap (future)."""

    feature: Mapped[str] = mapped_column(String(120))
    direction: Mapped[str] = mapped_column(String(8))
    """up | down | flat — direction of the model's response to this feature."""

    delta_pp_or_sensitivity: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_value: Mapped[str | None] = mapped_column(String(120), nullable=True)


class IntelligenceTelemetry(UUIDMixin, TenantMixin, TimestampMixin, Base):
    """One row per app/ai call — feeds the fallback / latency / cost dashboards.

    Populated by the app/ai gateway (not by callers). Lets the platform prove which calls
    hit the model vs. degraded to fallback, per feature.
    """
    __tablename__ = "intelligence_telemetry"

    call_class: Mapped[str] = mapped_column(String(20), index=True)
    """classify | rank | read | narrate | complex_plan."""

    feature: Mapped[str] = mapped_column(String(80), index=True)
    """assistant | weekly_review | meeting_brief | composer | change_radar | …"""

    engine_used: Mapped[str] = mapped_column(String(120))
    """The model that actually answered, e.g. "openai/gpt-oss-120b" or
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free" (OpenRouter slugs run long),
    or "fallback_rules" / "fallback_template" when no live model answered."""

    fallback_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    """Non-null when the call fell back — the provider error text that caused it."""

    prompt_template_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    schema_ok: Mapped[bool] = mapped_column(default=True)
    """False when the model returned a payload that failed Pydantic validation."""
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    """FastAPI request id — join back to the access log."""
    principal_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    """User whose action triggered the call. Nullable for worker jobs."""
