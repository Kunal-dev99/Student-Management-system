"""Funding contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.funding.constants import FundingStatus, FundingType


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


class ChangeRequest(_Camel):
    funding_type: FundingType
    funding_source_id: uuid.UUID | None = None
    stipend_amount: Decimal | None = None
    currency: str | None = None


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
