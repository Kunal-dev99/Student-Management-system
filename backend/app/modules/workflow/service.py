"""Workflow service — the task inbox and notification centre (arch §9, §11.5)."""
from __future__ import annotations

import uuid

from app.core.errors import NotFoundError, PermissionError
from app.core.principal import Principal
from app.modules.workflow.constants import NotificationStatus, TaskStatus
from app.modules.workflow.models import Notification, Task
from app.modules.workflow.repository import WorkflowRepository


class WorkflowService:
    def __init__(self, repo: WorkflowRepository) -> None:
        self.repo = repo
        self.session = repo.session

    async def my_tasks(self, principal: Principal, *, only_open: bool = True) -> list[Task]:
        return await self.repo.tasks_for(principal.user_id, principal.roles, only_open=only_open)

    def _can_act(self, principal: Principal, task: Task) -> bool:
        return task.assignee_user_id == principal.user_id or (
            task.assignee_role is not None and task.assignee_role in principal.roles
        )

    async def complete_task(self, task_id: uuid.UUID, principal: Principal) -> Task:
        task = await self.repo.get_task(task_id)
        if task is None:
            raise NotFoundError("Task not found")
        if not self._can_act(principal, task):
            raise PermissionError("This task is not in your queue")
        task.status = TaskStatus.done
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def my_notifications(self, principal: Principal) -> list[Notification]:
        return await self.repo.notifications_for(principal.user_id)

    async def mark_read(self, notification_id: uuid.UUID, principal: Principal) -> Notification:
        n = await self.repo.get_notification(notification_id)
        if n is None or n.recipient_user_id != principal.user_id:
            raise NotFoundError("Notification not found")
        n.status = NotificationStatus.read
        await self.session.commit()
        await self.session.refresh(n)
        return n
