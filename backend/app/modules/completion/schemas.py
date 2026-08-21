"""Completion contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.completion.constants import CompletionStatus


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class AwardOut(_Camel):
    id: uuid.UUID
    title: str
    award_type: str | None = None
    conferred_at: datetime | None = None


class CompletionOut(_Camel):
    id: uuid.UUID
    student_id: uuid.UUID
    status: CompletionStatus
    requirements_met_at: datetime | None = None
    award_confirmed_at: datetime | None = None
    graduation_date: date | None = None
    award: AwardOut | None = None
