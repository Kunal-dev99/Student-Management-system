"""Export contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.exports.constants import ExportStatus


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
