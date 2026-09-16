"""Export contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.exports.constants import AdvisoryStatus, ExportStatus, SpecVersionStatus


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class ExportRequest(_Camel):
    kind: str = "students_statutory"


class ExportJobOut(_Camel):
    id: uuid.UUID
    kind: str
    status: ExportStatus
    filename: str | None = None
    row_count: int | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


# --- ICR G5 — statutory advisory ingestion ---------------------------------

class AdvisoryIngestRequest(_Camel):
    pack_code: str = "HESA_STUDENT"
    academic_year: str | None = None       # a YEAR: directive in the text can supply this instead
    title: str = ""
    raw_text: str
    source: str = "paste"


class AdvisoryDecision(_Camel):
    note: str | None = None


class AdvisoryOut(_Camel):
    id: uuid.UUID
    pack_code: str
    academic_year: str
    title: str
    status: AdvisoryStatus
    source: str
    base_version: int
    parse_source: str
    changes: list[dict]
    proposed_fields: list[dict]
    proposed_rules: list[dict]
    created_at: datetime
    decided_at: datetime | None = None
    decision_note: str | None = None
    # Non-persisted parse warnings, present only on a freshly-ingested response.
    parse_warnings: list[str] = []


class SpecVersionOut(_Camel):
    id: uuid.UUID
    pack_code: str
    academic_year: str
    version: int
    name: str
    status: SpecVersionStatus
    field_count: int = 0
    source_advisory_id: uuid.UUID | None = None
    created_at: datetime
