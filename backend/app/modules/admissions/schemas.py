"""Admissions contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.admissions.constants import OfferStatus
from app.modules.student_record.constants import StudyMode


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class OfferCreate(_Camel):
    conditions: dict | None = None


class OfferOut(_Camel):
    id: uuid.UUID
    application_id: uuid.UUID
    status: OfferStatus
    conditions: dict | None = None
    issued_at: datetime | None = None
    responded_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


class AcceptRequest(_Camel):
    programme_id: uuid.UUID | None = None
    study_mode: StudyMode = StudyMode.full_time
    start_date: date | None = None
