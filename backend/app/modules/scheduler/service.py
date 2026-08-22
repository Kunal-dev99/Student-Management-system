"""Scheduled periodic jobs (arch §9.3).

Runs the checks a scheduled worker would run: generate milestones that fall due, flag funding
expiring within 90 days, and escalate tasks past their due date. There is no worker/broker in
this MVP, so the jobs are triggered by an admin endpoint — the same stand-in pattern as the
outbox dispatcher. Each job is idempotent enough to run repeatedly.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.funding.constants import FundingStatus
from app.modules.funding.models import FundingArrangement
from app.modules.progression.repository import ProgressionRepository
from app.modules.progression.service import ProgressionService
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.models import Student
from app.modules.workflow.constants import NotificationStatus, OPEN_TASK_STATES, TaskStatus
from app.modules.workflow.engine import WorkflowEngine
from app.modules.workflow.models import Notification, Task

FUNDING_HORIZON_DAYS = 90


class SchedulerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run_all(self) -> dict:
        return {
            # Returns come first: a student who returned today should be chased normally again.
            "studentsReturnedFromSuspension": await self._auto_return_suspensions(),
            "milestonesGenerated": await self._generate_due_milestones(),
            "fundingExpiringFlagged": await self._flag_funding_expiring(),
            "overdueTasksEscalated": await self._escalate_overdue_tasks(),
            "notificationsDelivered": await self._deliver_notifications(),
            "viewsRefreshed": "n/a (dashboards computed on demand)",
            "ranAt": datetime.now(timezone.utc).isoformat(),
        }

    async def _auto_return_suspensions(self) -> int:
        from app.modules.student_record.lifecycle import LifecycleService

        return await LifecycleService(self.session).auto_return_due()

    async def _paused_student_ids(self) -> set:
        """Students who are suspended or on leave — they must not be chased (Phase 6.5)."""
        from app.modules.student_record.constants import PAUSED_STATUSES

        rows = await self.session.execute(
            select(Student.id).where(Student.status.in_(list(PAUSED_STATUSES)))
        )
        return {r[0] for r in rows.all()}

    async def _deliver_notifications(self) -> int:
        # Real delivery: in-app -> sent, plus best-effort email per the recipient's preferences.
        from app.modules.notifications.service import NotificationService

        result = await NotificationService(self.session).deliver_queued()
        return result["delivered"]

    async def _generate_due_milestones(self) -> int:
        stmt = select(Student).where(
            Student.programme_id.is_not(None),
            Student.status.in_([StudentStatus.registered, StudentStatus.active]),
        )
        students = (await self.session.execute(stmt)).scalars().all()
        prog = ProgressionService(ProgressionRepository(self.session))
        generated = 0
        for st in students:
            existing = await prog.repo.milestones_for_student(st.id)
            if not existing:  # no milestones yet -> generate the first due one
                if await prog._generate_next(st) is not None:
                    generated += 1
        await self.session.commit()
        return generated

    async def _flag_funding_expiring(self) -> int:
        cutoff = date.today() + timedelta(days=FUNDING_HORIZON_DAYS)
        stmt = select(FundingArrangement).where(
            FundingArrangement.status == FundingStatus.active,
            FundingArrangement.valid_to.is_not(None),
            FundingArrangement.valid_to >= date.today(),
            FundingArrangement.valid_to <= cutoff,
        )
        arrangements = (await self.session.execute(stmt)).scalars().all()
        engine = WorkflowEngine(self.session)
        paused = await self._paused_student_ids()
        flagged = 0
        for fa in arrangements:
            if fa.student_id in paused:
                continue  # suspended/on-leave students are not chased about funding
            # Dedup: skip if an open task already exists for this arrangement.
            open_task = (await self.session.execute(
                select(Task).where(
                    Task.aggregate_type == "funding_arrangement",
                    Task.aggregate_id == fa.id,
                    Task.status.in_(OPEN_TASK_STATES),
                )
            )).scalars().first()
            if open_task is None:
                engine.create_task(
                    title=f"Plan funding renewal — arrangement expires {fa.valid_to}",
                    assignee_role="PGR Administrator",
                    aggregate_type="funding_arrangement", aggregate_id=fa.id,
                    payload={"studentId": str(fa.student_id), "expiresOn": fa.valid_to.isoformat()},
                )
                flagged += 1
        await self.session.commit()
        return flagged

    async def _escalate_overdue_tasks(self) -> int:
        # Escalate active tasks only; blocked = already escalated, so this stays idempotent.
        now = datetime.now(timezone.utc)
        stmt = select(Task).where(
            Task.due_at.is_not(None), Task.due_at < now,
            Task.status.in_([TaskStatus.open, TaskStatus.in_progress]),
        )
        tasks = (await self.session.execute(stmt)).scalars().all()
        paused = {str(sid) for sid in await self._paused_student_ids()}
        escalated = 0
        for t in tasks:
            # Don't escalate work about a student whose journey is paused (Phase 6.5).
            if paused and str((t.payload or {}).get("studentId") or "") in paused:
                continue
            t.status = TaskStatus.blocked  # escalation: flag for attention
            escalated += 1
        await self.session.commit()
        return escalated
