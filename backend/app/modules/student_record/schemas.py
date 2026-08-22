"""Student record contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.student_record.constants import (
    LifecycleEventStatus,
    LifecycleEventType,
    StudentStatus,
    StudyMode,
)


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class ResearchProjectOut(_Camel):
    id: uuid.UUID
    research_topic: str | None = None
    research_group: str | None = None


class StudentOut(_Camel):
    id: uuid.UUID
    person_id: uuid.UUID
    student_ref: str
    programme_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    research_area_id: uuid.UUID | None = None
    start_date: date | None = None
    expected_end_date: date | None = None
    # The date agreed at registration, before any suspension/extension (Phase 6.5).
    original_expected_end_date: date | None = None
    study_mode: StudyMode
    status: StudentStatus
    created_at: datetime
    project: ResearchProjectOut | None = None


class LifecycleEventRequest(_Camel):
    event_type: LifecycleEventType
    reason: str
    start_date: date
    end_date: date | None = None            # required for a suspension
    extension_days: int | None = None       # required for an extension
    new_mode: StudyMode | None = None       # required for a mode change


class LifecycleDecision(_Camel):
    note: str | None = None


class ReturnRequest(_Camel):
    returned_on: date | None = None


class LifecycleEventOut(_Camel):
    id: str
    student_id: str
    event_type: LifecycleEventType
    status: LifecycleEventStatus
    start_date: str
    end_date: str | None = None
    actual_end_date: str | None = None
    extension_days: int | None = None
    previous_mode: StudyMode | None = None
    new_mode: StudyMode | None = None
    reason: str
    days_applied: int | None = None
    decision_note: str | None = None
    decided_at: str | None = None


class StudentUpdate(_Camel):
    status: StudentStatus | None = None
    study_mode: StudyMode | None = None
    expected_end_date: date | None = None
    research_area_id: uuid.UUID | None = None


class StudentSummary(_Camel):
    id: uuid.UUID
    student_ref: str
    person_id: uuid.UUID
    person_name: str
    status: StudentStatus
    study_mode: StudyMode
    start_date: date | None = None
    programme_id: uuid.UUID | None = None
    research_topic: str | None = None
    # Supervisors and funding fold in as those modules land (BE-1.6 / BE-1.8).
    supervisors: list = []
    funding: list = []
