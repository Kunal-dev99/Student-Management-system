"""Taught-lifecycle contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.taught.constants import (
    AssessmentType,
    ClassificationBand,
    ModuleEnrolmentStatus,
    ModuleOutcome,
)


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# --- Modules & assessments (programme configuration) ---

class ModuleCreate(_Camel):
    code: str
    title: str
    credits: int = 0
    term: str | None = None
    level: int = 7
    is_core: bool = True
    convenor_person_id: uuid.UUID | None = None


class ModuleUpdate(_Camel):
    code: str | None = None
    title: str | None = None
    credits: int | None = None
    term: str | None = None
    level: int | None = None
    is_core: bool | None = None
    convenor_person_id: uuid.UUID | None = None


class AssessmentCreate(_Camel):
    title: str
    assessment_type: AssessmentType
    weight_pct: Decimal = Decimal("100.00")
    max_mark: Decimal = Decimal("100.00")
    due_date: date | None = None
    pass_mark: Decimal = Decimal("50.00")
    resit_allowed: bool = True
    resit_cap: Decimal | None = None


class AssessmentOut(_Camel):
    id: uuid.UUID
    module_id: uuid.UUID
    title: str
    assessment_type: AssessmentType
    weight_pct: Decimal
    max_mark: Decimal
    due_date: date | None = None
    pass_mark: Decimal = Decimal("50.00")
    resit_allowed: bool = True
    resit_cap: Decimal | None = None


class ModuleOut(_Camel):
    id: uuid.UUID
    programme_id: uuid.UUID
    code: str
    title: str
    credits: int
    term: str | None = None
    level: int = 7
    is_core: bool = True
    convenor_person_id: uuid.UUID | None = None
    assessments: list[AssessmentOut] = []


# --- Enrolments & results (per student) ---

class EnrolmentCreate(_Camel):
    module_id: uuid.UUID
    academic_year: str


class EnrolmentStatusRequest(_Camel):
    status: ModuleEnrolmentStatus


class ResultRecord(_Camel):
    assessment_id: uuid.UUID
    mark: Decimal | None = None
    grade: str | None = None
    is_resit: bool = False
    submitted_at: datetime | None = None


class ResultOut(_Camel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    mark: Decimal | None = None
    grade: str | None = None
    is_resit: bool = False
    attempt_number: int = 1
    capped: bool = False
    submitted_at: datetime | None = None
    marked_at: datetime | None = None


class EnrolmentOut(_Camel):
    id: uuid.UUID
    student_id: uuid.UUID
    module_id: uuid.UUID
    module_code: str | None = None
    module_title: str | None = None
    credits: int | None = None
    academic_year: str
    status: ModuleEnrolmentStatus
    module_mark: Decimal | None = None  # credit-weighted assessment mark for this module
    outcome: ModuleOutcome = ModuleOutcome.pending
    credits_awarded: int | None = None
    condoned: bool = False
    results: list[ResultOut] = []


# --- Dissertation ---

class DissertationUpsert(_Camel):
    title: str | None = None
    supervisor_person_id: uuid.UUID | None = None
    second_marker_person_id: uuid.UUID | None = None
    submitted_at: datetime | None = None
    first_mark: Decimal | None = None
    second_mark: Decimal | None = None
    mark: Decimal | None = None          # agreed mark
    grade: str | None = None
    word_count: int | None = None


class DissertationOut(_Camel):
    id: uuid.UUID
    student_id: uuid.UUID
    title: str | None = None
    supervisor_person_id: uuid.UUID | None = None
    supervisor_name: str | None = None
    second_marker_person_id: uuid.UUID | None = None
    second_marker_name: str | None = None
    submitted_at: datetime | None = None
    marked_at: datetime | None = None
    first_mark: Decimal | None = None
    second_mark: Decimal | None = None
    mark: Decimal | None = None
    grade: str | None = None
    word_count: int | None = None


class CondoneRequest(_Camel):
    condoned: bool = True


# --- Award / classification ---

class AwardOut(_Camel):
    student_id: uuid.UUID
    final_mark: Decimal | None = None
    classification: ClassificationBand | None = None
    credits_achieved: int | None = None
    decided_at: datetime | None = None


class TaughtRecordOut(_Camel):
    """Everything the student-360 taught panel needs in one call."""
    student_id: uuid.UUID
    programme_type: str
    total_credits_target: int | None = None
    credits_enrolled: int = 0
    enrolments: list[EnrolmentOut] = []
    dissertation: DissertationOut | None = None
    award: AwardOut | None = None
