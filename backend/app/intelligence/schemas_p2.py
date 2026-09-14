"""Pydantic contracts for Phase 2 — interventions, commitments, engagement."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
import uuid

from pydantic import BaseModel, ConfigDict


ActionType = Literal[
    "create_task",
    "prepare_meeting_brief",
    "request_funding_review",
    "open_review_evidence_check",
    "schedule_reassessment",
]
PlanStatus = Literal["draft", "confirmed", "cancelled", "expired"]
ActionStatus = Literal["pending", "executed", "failed", "skipped"]


class InterventionActionIn(BaseModel):
    action_type: ActionType
    target_ref: dict[str, Any]
    owner_ref: dict[str, Any] | None = None
    due_at: datetime | None = None
    payload: dict[str, Any] | None = None


class InterventionActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action_type: ActionType
    target_ref: dict[str, Any]
    owner_ref: dict[str, Any] | None = None
    due_at: datetime | None = None
    status: ActionStatus
    executed_at: datetime | None = None
    execution_ref: dict[str, Any] | None = None
    error_reason: str | None = None


class InterventionPlanCreate(BaseModel):
    case_ref: str
    student_id: uuid.UUID | None = None
    rationale: str
    source_signal: dict[str, Any] | None = None
    reassess_at: datetime | None = None
    actions: list[InterventionActionIn]


class InterventionPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_ref: str
    student_id: uuid.UUID | None = None
    rationale: str
    source_signal: dict[str, Any] | None = None
    reassess_at: datetime | None = None
    status: PlanStatus
    confirmed_at: datetime | None = None
    actions: list[InterventionActionOut] = []


class SupervisionCommitmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    meeting_id: uuid.UUID
    student_id: uuid.UUID
    text: str
    owner_person_or_role: str | None = None
    due_at: datetime | None = None
    status: Literal["open", "done", "cancelled"]
    dependency_ids: dict[str, Any] | None = None
    source: str


class EngagementSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    computed_at: datetime
    label: Literal["thriving", "steady", "drifting", "strained"]
    score: int
    drivers: dict[str, Any] | None = None
    engine: str


class EngagementTrajectoryOut(BaseModel):
    student_id: uuid.UUID
    points: list[EngagementSnapshotOut]
    recent_events: list[dict[str, Any]] = []
