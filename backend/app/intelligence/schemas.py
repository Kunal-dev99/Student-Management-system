"""Pydantic contracts for the intelligence layer (Phase 1).

These schemas are the shared language between the assistant, twin, intervention and
scenario surfaces. Every LLM call and every intelligence router response validates
through one of these — free-form dicts are refused at the boundary.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field


ClaimType = Literal[
    "deterministic_fact",
    "model_signal",
    "document_finding",
    "user_context",
    "missing_data",
]
ClaimStatus = Literal["verified", "inferred_for_review", "missing", "superseded"]
CallClass = Literal["classify", "rank", "read", "narrate", "complex_plan"]


class EvidenceClaimOut(BaseModel):
    """One factual claim underlying an AI-produced statement."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    artefact_id: uuid.UUID
    claim_type: ClaimType
    source_type: str
    source_id: str | None = None
    locator: dict[str, Any] | None = None
    value_hash: str | None = None
    as_of: datetime
    status: ClaimStatus = "verified"
    detail: dict[str, Any] | None = None


class EvidenceClaimCreate(BaseModel):
    """Write-side of an evidence claim — used when a producer records what it read."""
    artefact_id: uuid.UUID
    claim_type: ClaimType
    source_type: str
    source_id: str | None = None
    locator: dict[str, Any] | None = None
    value_hash: str | None = None
    as_of: datetime
    status: ClaimStatus = "verified"
    permission_scope: dict[str, Any] | None = None
    detail: dict[str, Any] | None = None


class TimeWindow(BaseModel):
    from_date: datetime | None = Field(default=None, alias="from")
    to_date: datetime | None = Field(default=None, alias="to")
    label: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class DomainSummary(BaseModel):
    """A per-domain compact view attached to a CaseContext."""
    domain: str
    highlights: list[str] = []
    counts: dict[str, int] = {}
    facts: list[dict[str, Any]] = []


class MissingSource(BaseModel):
    source: str
    reason: str


class CaseContext(BaseModel):
    """The typed working set behind Ask PGR, the Digital Twin and intervention planning.

    Deliberately bounded — no free-form transcript, no arbitrary retrieval; every field is
    either a resolved id/name/window or a small summary the intelligence layer built from
    row-scoped domain queries.
    """
    principal_scope: dict[str, Any]
    """Snapshot of who the caller is (user id, roles, allowed_ids). Small, JSON-safe."""

    student_id: uuid.UUID | None = None
    cohort_filter: dict[str, Any] | None = None
    """Only one of student_id / cohort_filter should be set for any given case."""

    time_window: TimeWindow | None = None
    active_filters: dict[str, Any] = {}
    domain_summaries: list[DomainSummary] = []
    missing_sources: list[MissingSource] = []
    pending_action_plan_id: uuid.UUID | None = None
    narrated_summary: dict[str, Any] | None = None
    """One-paragraph LLM-narrated summary + provenance; populated only when the caller
    passes `enable_llm=True` on the endpoint."""


class ActionDraft(BaseModel):
    """One command inside an intervention plan — bounded, allow-listed type."""
    action_type: Literal[
        "create_task",
        "prepare_meeting_brief",
        "request_funding_review",
        "open_review_evidence_check",
        "schedule_reassessment",
    ]
    target_ref: dict[str, Any]
    """{kind, id, label} — e.g. {"kind":"student","id":"...","label":"Marcus Bell"}."""

    owner_ref: dict[str, Any] | None = None
    """Resolved from existing supervisor relationship, workflow role or admin choice."""

    due_at: datetime | None = None
    """Nullable — the doc's rule: never invent a deadline the source didn't provide."""

    payload: dict[str, Any] | None = None
    """Small structured args the executing domain service will consume."""

    idempotency_key: str
    """case_ref + action_type + target + source_event."""


class ActionPlan(BaseModel):
    """Draft intervention plan — never executed until user confirms via existing services."""
    plan_id: uuid.UUID
    case_ref: str
    rationale: str
    actions: list[ActionDraft]
    reassess_at: datetime | None = None
    status: Literal["draft", "confirmed", "cancelled", "expired"] = "draft"


class PredictionSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    target: str
    model_version_id: uuid.UUID
    predicted_at: datetime
    probability: float
    threshold: float | None = None
    model_health: dict[str, Any] | None = None


class DriverSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prediction_id: uuid.UUID
    method: str
    feature: str
    direction: Literal["up", "down", "flat"]
    delta_pp_or_sensitivity: float | None = None
    baseline_value: str | None = None
    input_value: str | None = None


class RiskStorylineOut(BaseModel):
    """One student's score history for a given target + the drivers behind each move."""
    student_id: uuid.UUID
    target: str
    points: list[PredictionSnapshotOut]
    drivers_by_prediction: dict[uuid.UUID, list[DriverSnapshotOut]] = {}
    model_version_boundaries: list[dict[str, Any]] = []


class TelemetryEvent(BaseModel):
    """Written by app/ai for every model call — never by callers directly."""
    call_class: CallClass
    feature: str
    engine_used: str
    fallback_path: str | None = None
    prompt_template_version: str | None = None
    latency_ms: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_estimate_usd: float | None = None
    schema_ok: bool = True
    request_id: str | None = None
    principal_id: uuid.UUID | None = None
