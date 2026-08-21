"""Workflow contracts (camelCase over the wire)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.workflow.constants import NotificationStatus, TaskStatus


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class TaskOut(_Camel):
    id: uuid.UUID
    title: str
    assignee_role: str | None = None
    assignee_user_id: uuid.UUID | None = None
    due_at: datetime | None = None
    status: TaskStatus
    aggregate_type: str | None = None
    aggregate_id: uuid.UUID | None = None
    payload: dict | None = None
    created_at: datetime


class NotificationOut(_Camel):
    id: uuid.UUID
    channel: str
    template: str
    payload: dict | None = None
    status: NotificationStatus
    created_at: datetime


class WorkflowDefinitionCreate(_Camel):
    key: str
    name: str
    initial_state: str
    states: list[str]
    transitions: list[dict]
    activate: bool = True


class WorkflowDefinitionOut(_Camel):
    id: uuid.UUID
    key: str
    version: int
    name: str
    initial_state: str
    states: list
    transitions: list
    active: bool


class StartInstanceRequest(_Camel):
    key: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    context: dict | None = None


class EventRequest(_Camel):
    event: str


class WorkflowInstanceOut(_Camel):
    id: uuid.UUID
    definition_id: uuid.UUID
    aggregate_type: str
    aggregate_id: uuid.UUID
    current_state: str
    context: dict | None = None
    created_at: datetime
