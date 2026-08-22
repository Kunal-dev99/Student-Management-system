"""Progression contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.modules.progression.constants import (
    AppealStatus,
    MilestoneStatus,
    PanelRole,
    ProgressionOutcome,
)


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
    # Phase 4B.6 — conditional outcomes must carry written conditions; the panel may attach
    # an outcome letter. `requirePanel` overrides the programme's milestone-definition config
    # (review_panel.required); omit it to use that configuration.
    conditions: str | None = None
    outcome_letter: str | None = None
    require_panel: bool | None = None


class PanelMemberRequest(_Camel):
    person_id: uuid.UUID
    role: PanelRole
    is_independent: bool = False


class PanelMemberOut(_Camel):
    id: str
    person_id: str
    person_name: str
    role: PanelRole
    is_independent: bool


class AppealRequest(_Camel):
    grounds: str


class AppealDecisionRequest(_Camel):
    status: AppealStatus
    decision_note: str | None = None


class AppealOut(_Camel):
    id: str
    review_id: str
    student_id: str
    grounds: str
    status: AppealStatus
    submitted_at: str | None = None
    decided_at: str | None = None
    decision_note: str | None = None
