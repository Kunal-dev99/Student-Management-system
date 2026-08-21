"""Progression contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.modules.progression.constants import MilestoneStatus, ProgressionOutcome


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class MilestoneDefinitionCreate(_Camel):
    name: str = Field(min_length=1, max_length=200)
    due_offset_days: int = 0
    trigger: dict | None = None
    required_documents: dict | None = None
    review_panel: dict | None = None
    assessment_criteria: dict | None = None
    possible_outcomes: dict | None = None


class MilestoneDefinitionOut(_Camel):
    id: uuid.UUID
    programme_id: uuid.UUID
    name: str
    due_offset_days: int
    trigger: dict | None = None
    possible_outcomes: dict | None = None
    created_at: datetime


class ProgressionReviewOut(_Camel):
    id: uuid.UUID
    student_submission_ref: str | None = None
    panel_decision: ProgressionOutcome | None = None
    decided_at: datetime | None = None
    rationale: str | None = None


class MilestoneOut(_Camel):
    id: uuid.UUID
    student_id: uuid.UUID
    milestone_definition_id: uuid.UUID
    name: str
    due_date: date | None = None
    status: MilestoneStatus
    review: ProgressionReviewOut | None = None


class SubmitRequest(_Camel):
    student_submission_ref: str | None = None


class DecideRequest(_Camel):
    outcome: ProgressionOutcome
    rationale: str | None = None
