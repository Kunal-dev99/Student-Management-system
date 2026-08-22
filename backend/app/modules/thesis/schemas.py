"""Thesis contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.thesis.constants import (
    CorrectionKind,
    ExaminationOutcome,
    ExaminerType,
    ThesisStatus,
    VivaFormat,
)


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class ExaminationOut(_Camel):
    id: uuid.UUID
    viva_date: date | None = None
    viva_location: str | None = None
    viva_format: VivaFormat | None = None
    viva_scheduled_at: datetime | None = None
    outcome: ExaminationOutcome | None = None
    decided_at: datetime | None = None


class ThesisOut(_Camel):
    id: uuid.UUID
    student_id: uuid.UUID
    title: str | None = None
    status: ThesisStatus
    intention_to_submit_at: datetime | None = None
    submitted_at: datetime | None = None
    document_ref: str | None = None
    examination: ExaminationOut | None = None


class IntentionRequest(_Camel):
    title: str | None = None


class SubmitThesisRequest(_Camel):
    title: str | None = None
    document_ref: str | None = None


class OutcomeRequest(_Camel):
    outcome: ExaminationOutcome
    viva_date: date | None = None


class NominateRequest(_Camel):
    examiner_person_id: uuid.UUID
    examiner_type: ExaminerType = ExaminerType.internal
    affiliation: str | None = None
    conflict_of_interest: bool = False
    conflict_note: str | None = None


class ExaminerNominationOut(_Camel):
    id: uuid.UUID
    examiner_person_id: uuid.UUID
    examiner_name: str
    examiner_type: ExaminerType
    approved: bool
    affiliation: str | None = None
    conflict_of_interest: bool = False
    conflict_note: str | None = None


class ScheduleVivaRequest(_Camel):
    viva_date: date
    viva_format: VivaFormat = VivaFormat.in_person
    location: str | None = None


class CorrectionOut(_Camel):
    id: str
    kind: CorrectionKind
    deadline: str | None = None
    submitted_at: str | None = None
    approved_at: str | None = None
