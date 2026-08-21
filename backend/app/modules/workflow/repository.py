"""Workflow data access (queries only)."""
from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.workflow.constants import OPEN_TASK_STATES
from app.modules.workflow.models import Notification, Task


class WorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def tasks_for(self, user_id: uuid.UUID, roles: list[str], *, only_open: bool) -> list[Task]:
        conds = [Task.assignee_user_id == user_id]
        if roles:
            conds.append(Task.assignee_role.in_(roles))
        stmt = select(Task).where(or_(*conds))
        if only_open:
            stmt = stmt.where(Task.status.in_(OPEN_TASK_STATES))
        stmt = stmt.order_by(Task.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_task(self, task_id: uuid.UUID) -> Task | None:
        return (await self.session.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()

    async def notifications_for(self, user_id: uuid.UUID) -> list[Notification]:
        stmt = select(Notification).where(Notification.recipient_user_id == user_id).order_by(Notification.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_notification(self, notification_id: uuid.UUID) -> Notification | None:
        return (await self.session.execute(select(Notification).where(Notification.id == notification_id))).scalar_one_or_none()
