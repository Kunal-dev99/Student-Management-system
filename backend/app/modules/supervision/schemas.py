"""Supervision contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.supervision.constants import (
    MeetingFormat,
    SupervisionStatus,
    SupervisorRole,
)


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class AssignRequest(_Camel):
    supervisor_person_id: uuid.UUID
    role: SupervisorRole = SupervisorRole.primary
    weighting_pct: int | None = None


class EndRequest(_Camel):
    reason: str | None = None


class MeetingRequest(_Camel):
    supervisor_person_id: uuid.UUID | None = None
    met_on: date
    format: MeetingFormat = MeetingFormat.in_person
    duration_minutes: int | None = None
    notes: str | None = None
    actions: str | None = None
    next_meeting_on: date | None = None


class MeetingOut(_Camel):
    id: str
    student_id: str
    supervisor_person_id: str | None = None
    supervisor_name: str | None = None
    met_on: str
    format: MeetingFormat
    duration_minutes: int | None = None
    notes: str | None = None
    actions: str | None = None
    next_meeting_on: str | None = None
    student_confirmed: bool = False


class SupervisorOut(_Camel):
    id: uuid.UUID
    supervisor_person_id: uuid.UUID
    supervisor_name: str
    role: SupervisorRole
    status: SupervisionStatus
    valid_from: date
    valid_to: date | None = None


class CaseloadItem(_Camel):
    relationship_id: uuid.UUID
    student_id: uuid.UUID
    student_ref: str
    person_name: str
    role: SupervisorRole
    last_meeting_on: str | None = None
    meeting_overdue: bool = False
