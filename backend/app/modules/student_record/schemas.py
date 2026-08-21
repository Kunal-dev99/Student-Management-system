"""Student record contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.student_record.constants import StudentStatus, StudyMode


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
    study_mode: StudyMode
    status: StudentStatus
    created_at: datetime
    project: ResearchProjectOut | None = None


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
