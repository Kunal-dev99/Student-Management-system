"""Digital Twin schemas — StudentTwinSnapshot + PressurePoint + DependencyEdge.

A twin is a derived read model: it composes existing authoritative rows into a
single time-aware view of a student's state. It is never persisted to the source
tables and never mutates state.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel


class PressurePoint(BaseModel):
    kind: Literal[
        "milestone_due", "milestone_overdue", "supervision_gap",
        "funding_expiring", "no_active_funding", "thesis_correction_window",
    ]
    label: str
    when: date | datetime | None = None
    weight: int
    """Deterministic weighting the twin uses to rank pressure points."""

    evidence: dict[str, Any] | None = None
    """Small ref back to the source row (kind, id, field)."""


class DependencyEdge(BaseModel):
    """A "this cannot proceed until that" hop between records."""
    from_ref: dict[str, Any]
    to_ref: dict[str, Any]
    reason: str


class ModelSignal(BaseModel):
    target: str
    probability: float
    model_version_id: uuid.UUID | None = None
    model_health: Literal["healthy", "review", "unknown"] = "unknown"


class NarratedState(BaseModel):
    body: str
    source: str  # "model" | "fallback"
    model: str | None = None


class StudentTwinSnapshot(BaseModel):
    student_id: uuid.UUID
    as_of: datetime
    state: dict[str, Any]
    """Current headline state: name, status, programme, mode, start/expected end."""

    pressure_points: list[PressurePoint] = []
    dependencies: list[DependencyEdge] = []
    model_signals: list[ModelSignal] = []
    blockers: list[str] = []
    narrated_state: NarratedState | None = None
    """Optional one-paragraph summary; populated only when `enable_llm=True` at the
    call site. Every figure it quotes comes from `state` / `pressure_points` verbatim;
    the deterministic fallback template runs when the model is off."""
