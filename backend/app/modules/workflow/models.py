"""Workflow engine ORM models (arch §8.12, §9.1). Portable types (D-04).

- Task: a unit of human work, assigned to a role or a specific user.
- Notification: an outbound message to a user.
- OutboxEvent: a domain event written in the same transaction as the state change, for
  reliable at-least-once delivery to integrations (arch §9.4, §10.2).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.modules.workflow.constants import NotificationStatus, TaskStatus


class WorkflowDefinition(UUIDMixin, TimestampMixin, Base):
    """A named, versioned state machine defined in data (arch §9.1) — new flows without code."""
    __tablename__ = "workflow_definition"

    key: Mapped[str] = mapped_column(String(80), index=True)     # e.g. "onboarding"
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(200))
    initial_state: Mapped[str] = mapped_column(String(80))
    states: Mapped[list] = mapped_column(JSON)                   # ["pending", "in_progress", "complete"]
    transitions: Mapped[list] = mapped_column(JSON)             # [{"from","on","to","action"?}]
    active: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (Index("uq_workflow_def_key_version", "key", "version", unique=True),)


class WorkflowInstance(UUIDMixin, TimestampMixin, Base):
    """A running flow bound to an aggregate (arch §9.1)."""
    __tablename__ = "workflow_instance"

    definition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_definition.id"), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(50))
    aggregate_id: Mapped[uuid.UUID] = mapped_column()
    current_state: Mapped[str] = mapped_column(String(80))
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Task(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "task"

    title: Mapped[str] = mapped_column(String(300))
    assignee_role: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus, name="task_status"), default=TaskStatus.open)
    # What this task is about (e.g. student / application / milestone).
    aggregate_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    aggregate_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # F5 — SLA clock. sla_target_seconds is the promised turnaround. sla_started_at defaults to
    # task creation; the worker computes elapsed and flips sla_breached when target is exceeded.
    # working_days_only is respected by the elapsed-time computation on the report side.
    sla_target_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sla_working_days_only: Mapped[bool] = mapped_column(Boolean, default=False)
    sla_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_breached: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    __table_args__ = (Index("ix_task_role_status", "assignee_role", "status"),)


class Notification(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "notification"

    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(30), default="in_app")
    template: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status"), default=NotificationStatus.queued
    )


class OutboxEvent(UUIDMixin, Base):
    __tablename__ = "outbox_event"

    aggregate_type: Mapped[str] = mapped_column(String(50), index=True)
    aggregate_id: Mapped[uuid.UUID] = mapped_column()
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Phase 4A.2 — at-least-once delivery with retry/backoff and a dead-letter terminal state.
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    dead_lettered: Mapped[bool] = mapped_column(Boolean, default=False)
