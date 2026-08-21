"""Supervision contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.supervision.constants import SupervisionStatus, SupervisorRole


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class AssignRequest(_Camel):
    supervisor_person_id: uuid.UUID
    role: SupervisorRole = SupervisorRole.primary


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
