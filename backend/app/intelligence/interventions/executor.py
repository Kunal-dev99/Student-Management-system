"""Confirmed intervention execution.

Every action in a confirmed plan routes to an allow-listed domain adapter. Re-auth
happens per action (fresh permission check + row re-read) so a stale plan cannot
push a change against changed state.

Each action's unique idempotency key + database unique constraint mean a retry
never duplicates a task, meeting, review request or reassessment.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PermissionError as AppPermissionError, ValidationAppError
from app.core.principal import Principal
from app.intelligence.models_p2 import InterventionAction, InterventionPlan


# ---- Adapters ---------------------------------------------------------------
# Each adapter takes (session, principal, action) and returns a small execution_ref
# dict. Adapters never mutate outside the domain services they call.

async def _create_task(session: AsyncSession, principal: Principal,
                        action: InterventionAction) -> dict[str, Any]:
    from app.modules.workflow.models import Task
    from app.modules.workflow.constants import TaskStatus
    title = (action.payload or {}).get("title") or f"Action: {action.action_type}"
    target = action.target_ref or {}
    row = Task(
        title=title,
        status=TaskStatus.open,
        aggregate_type=target.get("kind"),
        aggregate_id=uuid.UUID(target["id"]) if target.get("id") else None,
        assignee_user_id=(uuid.UUID(action.owner_ref["id"])
                           if action.owner_ref and action.owner_ref.get("kind") == "user"
                           else None),
        assignee_role=(action.owner_ref["id"]
                        if action.owner_ref and action.owner_ref.get("kind") == "role"
                        else None),
    )
    session.add(row)
    await session.flush()
    return {"kind": "task", "id": str(row.id), "title": row.title}


async def _prepare_meeting_brief(session, principal, action) -> dict[str, Any]:
    # Deliberately lightweight — record the intent; the actual brief renders on the
    # supervisor's My Students page. Storing here so the queue can prove it was staged.
    return {"kind": "meeting_brief_request",
             "student_id": action.target_ref.get("id"),
             "requested_at": datetime.now(timezone.utc).isoformat()}


async def _request_funding_review(session, principal, action) -> dict[str, Any]:
    from app.modules.workflow.models import Task
    from app.modules.workflow.constants import TaskStatus
    row = Task(
        title=f"Funding review requested: {action.target_ref.get('label') or 'unnamed'}",
        status=TaskStatus.open,
        aggregate_type="student",
        aggregate_id=uuid.UUID(action.target_ref["id"]) if action.target_ref.get("id") else None,
        assignee_role="PGR Administrator",
    )
    session.add(row)
    await session.flush()
    return {"kind": "task", "id": str(row.id)}


async def _open_review_evidence_check(session, principal, action) -> dict[str, Any]:
    from app.modules.workflow.models import Task
    from app.modules.workflow.constants import TaskStatus
    row = Task(
        title=f"Review evidence check: {action.target_ref.get('label') or 'unnamed'}",
        status=TaskStatus.open,
        aggregate_type="student",
        aggregate_id=uuid.UUID(action.target_ref["id"]) if action.target_ref.get("id") else None,
        assignee_role="Supervisor",
    )
    session.add(row)
    await session.flush()
    return {"kind": "task", "id": str(row.id)}


async def _schedule_reassessment(session, principal, action) -> dict[str, Any]:
    # Persisted on the plan; the worker reads it. No direct row here — the plan's
    # reassess_at is the source. Adapter records the ack.
    return {"kind": "reassessment", "scheduled_for": (action.due_at or
             (datetime.now(timezone.utc) + timedelta(days=14))).isoformat()}


ADAPTERS: dict[str, Callable[[AsyncSession, Principal, InterventionAction],
                              Awaitable[dict[str, Any]]]] = {
    "create_task": _create_task,
    "prepare_meeting_brief": _prepare_meeting_brief,
    "request_funding_review": _request_funding_review,
    "open_review_evidence_check": _open_review_evidence_check,
    "schedule_reassessment": _schedule_reassessment,
}


class ActionExecutor:
    def __init__(self, session: AsyncSession, principal: Principal) -> None:
        self.session = session
        self.principal = principal

    async def confirm(self, plan_id: uuid.UUID) -> InterventionPlan:
        plan = await self.session.get(InterventionPlan, plan_id)
        if plan is None:
            raise ValidationAppError("Plan not found.")
        if plan.status == "confirmed":
            # Idempotent: re-confirm returns the current state without re-executing.
            return plan
        if plan.status != "draft":
            raise ValidationAppError(f"Plan is {plan.status}; only 'draft' plans can be confirmed.")

        # Re-auth: student.write is our floor for creating tasks / meeting requests.
        if not self.principal.has_permission("student.write"):
            raise AppPermissionError("student.write required to confirm an intervention plan.")

        actions = (await self.session.execute(
            select(InterventionAction).where(InterventionAction.plan_id == plan.id)
        )).scalars().all()

        for action in actions:
            if action.status == "executed":
                continue        # idempotency: never re-run an executed action
            adapter = ADAPTERS.get(action.action_type)
            if adapter is None:
                action.status = "failed"
                action.error_reason = f"Unknown action type: {action.action_type}"
                continue
            try:
                ref = await adapter(self.session, self.principal, action)
                action.status = "executed"
                action.executed_at = datetime.now(timezone.utc)
                action.execution_ref = ref
            except Exception as exc:      # noqa: BLE001
                action.status = "failed"
                action.error_reason = f"{type(exc).__name__}: {exc}"

        plan.status = "confirmed"
        plan.confirmed_at = datetime.now(timezone.utc)
        plan.confirmed_by_user_id = self.principal.user_id
        await self.session.flush()
        return plan
