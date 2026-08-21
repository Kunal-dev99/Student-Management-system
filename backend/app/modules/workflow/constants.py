"""Workflow / task / notification enumerations (arch §8.2, §9)."""
from __future__ import annotations

import enum


class TaskStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"
    cancelled = "cancelled"


class NotificationStatus(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    read = "read"
    failed = "failed"


class WorkflowState(str, enum.Enum):
    created = "created"
    active = "active"
    waiting = "waiting"
    completed = "completed"
    cancelled = "cancelled"


OPEN_TASK_STATES = {TaskStatus.open, TaskStatus.in_progress, TaskStatus.blocked}
