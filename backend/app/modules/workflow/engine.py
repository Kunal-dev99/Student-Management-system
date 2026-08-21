"""The reusable workflow engine (arch §9).

Other modules' services call this to create human tasks, queue notifications, and record
domain events to the outbox — all on the SAME session, so they commit atomically with the
triggering state change (arch §9.4 guarantee). The engine never commits.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.workflow.models import Notification, OutboxEvent, Task


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowEngine:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def emit(self, aggregate_type: str, aggregate_id: uuid.UUID, event_type: str, payload: dict | None = None) -> OutboxEvent:
        event = OutboxEvent(
            aggregate_type=aggregate_type, aggregate_id=aggregate_id,
            event_type=event_type, payload=payload, created_at=_now(),
        )
        self.session.add(event)
        return event

    def create_task(
        self, *, title: str, assignee_role: str | None = None, assignee_user_id: uuid.UUID | None = None,
        aggregate_type: str | None = None, aggregate_id: uuid.UUID | None = None,
        payload: dict | None = None, due_at: datetime | None = None,
    ) -> Task:
        task = Task(
            title=title, assignee_role=assignee_role, assignee_user_id=assignee_user_id,
            aggregate_type=aggregate_type, aggregate_id=aggregate_id, payload=payload, due_at=due_at,
        )
        self.session.add(task)
        return task

    def notify(self, *, recipient_user_id: uuid.UUID, template: str, payload: dict | None = None, channel: str = "in_app") -> Notification:
        n = Notification(recipient_user_id=recipient_user_id, template=template, payload=payload, channel=channel)
        self.session.add(n)
        return n
