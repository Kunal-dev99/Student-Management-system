"""Recruitment contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.modules.recruitment.constants import (
    ApplicationRoute,
    CandidateStage,
    OpportunityFunding,
    OpportunityStatus,
)


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# --- Opportunities ---
class OpportunityCreate(_Camel):
    title: str = Field(min_length=1, max_length=300)
    research_area_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    principal_supervisor_id: uuid.UUID | None = None
    stipend_amount: Decimal | None = None
    currency: str | None = Field(default=None, max_length=3)
    eligibility: str | None = None
    start_date: date | None = None
    expected_duration_months: int | None = None
    positions_available: int = 1
    # Phase 6.1 — provenance: the demand this position answers and the award funding it.
    research_demand_id: uuid.UUID | None = None
    research_award_id: uuid.UUID | None = None
    # W1.1 — explicit funding shape; defaults on the DB side so this may be omitted.
    opportunity_type: OpportunityFunding | None = None


class OpportunityUpdate(_Camel):
    title: str | None = None
    eligibility: str | None = None
    stipend_amount: Decimal | None = None
    positions_available: int | None = None
    opportunity_type: OpportunityFunding | None = None


class OpportunityOut(_Camel):
    id: uuid.UUID
    title: str
    research_area_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    principal_supervisor_id: uuid.UUID | None = None
    stipend_amount: Decimal | None = None
    currency: str | None = None
    eligibility: str | None = None
    start_date: date | None = None
    expected_duration_months: int | None = None
    positions_available: int
    positions_filled: int = 0
    research_demand_id: uuid.UUID | None = None
    research_award_id: uuid.UUID | None = None
    status: OpportunityStatus
    opportunity_type: OpportunityFunding = OpportunityFunding.funded
    created_at: datetime


class TransitionRequest(_Camel):
    to_status: OpportunityStatus


# --- Applications ---
class ApplicationCreate(_Camel):
    person_id: uuid.UUID
    route: ApplicationRoute
    research_opportunity_id: uuid.UUID | None = None
    research_area_id: uuid.UUID | None = None
    proposal_document_ref: str | None = None


class StageHistoryOut(_Camel):
    id: uuid.UUID
    from_stage: CandidateStage | None = None
    to_stage: CandidateStage
    reason: str | None = None
    moved_at: datetime


class AssessmentOut(_Camel):
    id: uuid.UUID
    decision: str | None = None
    rationale: str | None = None
    criteria: dict | None = None
    assessed_at: datetime


class ApplicationOut(_Camel):
    id: uuid.UUID
    person_id: uuid.UUID
    route: ApplicationRoute
    research_opportunity_id: uuid.UUID | None = None
    research_area_id: uuid.UUID | None = None
    proposal_document_ref: str | None = None
    current_stage: CandidateStage
    submitted_at: datetime | None = None
    created_at: datetime
    # F3 — fee status + visa gate fields
    fee_status: str | None = "unknown"
    visa_required: bool = False
    visa_check_completed_at: datetime | None = None
    history: list[StageHistoryOut] = Field(default_factory=list)
    assessments: list[AssessmentOut] = Field(default_factory=list)


class AdvanceRequest(_Camel):
    to_stage: CandidateStage
    reason: str | None = None


class AssessRequest(_Camel):
    decision: str
    rationale: str | None = None
    criteria: dict | None = None


class PipelineOut(_Camel):
    counts: dict[str, int]
    total: int
