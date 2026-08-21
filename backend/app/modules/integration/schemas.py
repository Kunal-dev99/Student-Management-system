"""Integration contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.integration.constants import Direction, IntegrationStatus


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class IntegrationLogOut(_Camel):
    id: uuid.UUID
    direction: Direction
    system: str
    event_type: str
    aggregate_type: str | None = None
    aggregate_id: uuid.UUID | None = None
    source_id: str | None = None
    status: IntegrationStatus
    detail: dict | None = None
    created_at: datetime


class DispatchResult(_Camel):
    dispatched: int
    outbound_calls: int
    failed: int = 0
    dead_lettered: int = 0


class DeadLetterOut(_Camel):
    id: uuid.UUID
    event_type: str
    aggregate_type: str | None = None
    aggregate_id: uuid.UUID | None = None
    attempts: int
    last_error: str | None = None
    created_at: datetime


class IntegrationOverview(_Camel):
    pending: int
    dead_letter_count: int = 0
    logs: list[IntegrationLogOut]
    dead_letters: list[DeadLetterOut] = []
