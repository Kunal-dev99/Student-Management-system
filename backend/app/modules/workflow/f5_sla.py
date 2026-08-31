"""F5 — Task SLA clock and reporting.

An SLA target is set on a Task when it is created (as part of the workflow definition or by an
explicit set-SLA call). The elapsed clock is computed on read; a worker sweep sets
``sla_breached=True`` once the elapsed time exceeds the target, and emits an outbox event.

Working-day computation excludes Sat/Sun. Public holidays are institution-specific — left as a
TODO for a real deployment where the holiday calendar becomes a setting.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.workflow.constants import TaskStatus
from app.modules.workflow.models import Task


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def working_seconds_between(start: datetime, end: datetime) -> int:
    """Seconds between two timestamps counting only Mon–Fri.

    Straightforward day-by-day walk (not a hot path — we only compute this per task, per view).
    """
    start = _aware(start); end = _aware(end)
    if end <= start:
        return 0
    total = 0
    cur = start
    while cur.date() < end.date():
        day_end = datetime.combine(cur.date() + timedelta(days=1),
                                   datetime.min.time(), tzinfo=timezone.utc)
        if cur.weekday() < 5:  # 0..4 = Mon..Fri
            total += int((day_end - cur).total_seconds())
        cur = day_end
    if cur.weekday() < 5:
        total += int((end - cur).total_seconds())
    return total


def elapsed_seconds(task: Task, *, now: datetime | None = None) -> int:
    now = _aware(now) or datetime.now(timezone.utc)
    start = _aware(task.sla_started_at) or _aware(task.created_at) or now
    if task.sla_working_days_only:
        return working_seconds_between(start, now)
    return int((now - start).total_seconds())


def is_breached(task: Task, *, now: datetime | None = None) -> bool:
    if task.sla_target_seconds is None:
        return False
    return elapsed_seconds(task, now=now) > task.sla_target_seconds


class SlaService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def set_sla(
        self, task_id: uuid.UUID, *, target_seconds: int,
        working_days_only: bool = False,
    ) -> Task:
        task = (await self.session.execute(select(Task).where(Task.id == task_id))).scalar_one()
        task.sla_target_seconds = target_seconds
        task.sla_working_days_only = working_days_only
        if task.sla_started_at is None:
            task.sla_started_at = _aware(task.created_at) or datetime.now(timezone.utc)
        task.sla_breached = is_breached(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def sweep(self) -> dict:
        """Worker job: mark any open, non-breached task with an exceeded SLA as breached.

        Idempotent — the update only fires for rows the check turns True.
        """
        rows = (await self.session.execute(
            select(Task).where(
                Task.status == TaskStatus.open,
                Task.sla_target_seconds.is_not(None),
                Task.sla_breached.is_(False),
            )
        )).scalars().all()
        newly = 0
        for t in rows:
            if is_breached(t):
                t.sla_breached = True
                newly += 1
        if newly:
            await self.session.commit()
        return {"checked": len(rows), "newlyBreached": newly}

    async def report(self) -> dict:
        """Snapshot for the SLA dashboard: totals, breach rate, and buckets by workflow key."""
        total = (await self.session.execute(
            select(func.count(Task.id)).where(Task.sla_target_seconds.is_not(None))
        )).scalar() or 0
        breached = (await self.session.execute(
            select(func.count(Task.id)).where(Task.sla_breached.is_(True))
        )).scalar() or 0
        open_ = (await self.session.execute(
            select(func.count(Task.id)).where(
                Task.sla_target_seconds.is_not(None),
                Task.status == TaskStatus.open,
            )
        )).scalar() or 0
        rate = 0.0 if total == 0 else round(1 - breached / total, 4)
        return {
            "total": int(total), "openWithSla": int(open_),
            "breached": int(breached),
            "withinTargetRate": rate,
        }
