"""Funding contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.funding.constants import (
    FundingStatus,
    FundingType,
    PaymentFrequency,
    PaymentStatus,
    WaiverKind,
)


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class FundingSourceOut(_Camel):
    id: uuid.UUID
    name: str
    funder_type: str | None = None


class ArrangementCreate(_Camel):
    funding_type: FundingType
    funding_source_id: uuid.UUID | None = None
    stipend_amount: Decimal | None = None
    currency: str | None = None
    valid_from: date | None = None
    # Phase 4B.7 — finance detail for reconciliation and blended funding.
    cost_centre: str | None = None
    project_code: str | None = None
    funder_reference: str | None = None
    contribution_pct: int | None = None
    research_award_id: uuid.UUID | None = None


class ChangeRequest(_Camel):
    funding_type: FundingType
    funding_source_id: uuid.UUID | None = None
    stipend_amount: Decimal | None = None
    currency: str | None = None
    cost_centre: str | None = None
    project_code: str | None = None
    funder_reference: str | None = None
    contribution_pct: int | None = None
    research_award_id: uuid.UUID | None = None


class ArrangementOut(_Camel):
    id: uuid.UUID
    student_id: uuid.UUID
    funding_type: FundingType
    funding_source_id: uuid.UUID | None = None
    funding_source_name: str | None = None
    stipend_amount: Decimal | None = None
    currency: str | None = None
    valid_from: date
    valid_to: date | None = None
    status: FundingStatus
    created_at: datetime
    cost_centre: str | None = None
    project_code: str | None = None
    funder_reference: str | None = None
    contribution_pct: int | None = None
    research_award_id: uuid.UUID | None = None
    payment_frequency: PaymentFrequency | None = None


# --- Phase 4B.7 — stipend payments ---

class ScheduleRequest(_Camel):
    frequency: PaymentFrequency = PaymentFrequency.monthly
    instalments: int | None = None
    first_due: date | None = None
    annual_amount: Decimal | None = None


class PaymentOut(_Camel):
    id: str
    arrangement_id: str
    student_id: str
    sequence: int
    due_date: str
    amount: str
    currency: str | None = None
    status: PaymentStatus
    paid_on: str | None = None
    finance_reference: str | None = None
    note: str | None = None


class MarkPaidRequest(_Camel):
    paid_on: date | None = None
    finance_reference: str | None = None


class PaymentStatusRequest(_Camel):
    status: PaymentStatus
    note: str | None = None


# --- Phase 4B.7 — fee waivers ---

class WaiverCreate(_Camel):
    kind: WaiverKind
    amount: Decimal | None = None
    percentage: int | None = None
    currency: str | None = None
    academic_year: str | None = None
    arrangement_id: uuid.UUID | None = None
    note: str | None = None


class WaiverOut(_Camel):
    id: str
    student_id: str
    arrangement_id: str | None = None
    kind: WaiverKind
    amount: str | None = None
    percentage: int | None = None
    currency: str | None = None
    academic_year: str | None = None
    approved: bool = False
    note: str | None = None
