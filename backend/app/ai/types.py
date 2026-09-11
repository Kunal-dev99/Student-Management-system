"""Shapes the AI layer produces and consumes.

Each shape is bounded on receipt — validation rejects anything outside it and the caller
gets a deterministic fallback instead. Deliberately narrow: three shapes cover every AI
use case in the app.
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------- shared inputs

class Candidate(BaseModel):
    """One row in a bounded list the model may rank. The id is the only identifier the
    model is allowed to return — anything else is a made-up pick and gets rejected."""

    id: str
    label: str
    score: float | None = None
    facts: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    """Deterministic figures the narrator paragraph is grounded against.

    Every numeric value the model may quote must appear in `figures`; the caller renders
    them verbatim in the UI beside the prose so the reader can verify.
    """

    figures: dict[str, str] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------- shape results

T = TypeVar("T", bound=BaseModel)


class Provenance(BaseModel):
    """Attached to every result so the UI can mark it as AI or fallback and show the model."""

    source: str  # "model" or "fallback"
    model: str | None = None
    latency_ms: int | None = None
    reason: str | None = None  # why the fallback ran, if it did


class RankPick(BaseModel):
    id: str
    reasoning: str


class RankResult(BaseModel):
    picks: list[RankPick]
    provenance: Provenance


class ReadResult(BaseModel, Generic[T]):
    fields: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    needs_manual: bool = False
    provenance: Provenance


class ClassifyResult(BaseModel):
    label: str
    reasoning: str
    provenance: Provenance


class Narration(BaseModel):
    body: str
    provenance: Provenance
