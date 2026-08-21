"""Thesis contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.thesis.constants import ExaminationOutcome, ExaminerType, ThesisStatus


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class ExaminationOut(_Camel):
    id: uuid.UUID
    viva_date: date | None = None
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


class ExaminerNominationOut(_Camel):
    id: uuid.UUID
    examiner_person_id: uuid.UUID
    examiner_name: str
    examiner_type: ExaminerType
    approved: bool
