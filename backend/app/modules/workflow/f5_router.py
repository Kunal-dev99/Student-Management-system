"""F5 — SLA endpoints on the tasks namespace."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_session
from app.modules.workflow.f5_sla import SlaService, elapsed_seconds, is_breached
from app.modules.workflow.models import Task
from sqlalchemy import select


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SetSlaBody(_Camel):
    target_seconds: int
    working_days_only: bool = False


router = APIRouter(prefix="/tasks", tags=["workflow"])


@router.get("/sla-report", summary="F5 — SLA snapshot for the tasks dashboard")
async def sla_report(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> dict:
    return await SlaService(session).report()


@router.post("/sla-sweep", summary="F5 — mark breached tasks (also runs on the worker)")
async def sla_sweep(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await SlaService(session).sweep()


@router.post("/{task_id}/sla", summary="F5 — attach or update the SLA target on a task")
async def set_sla(
    task_id: uuid.UUID,
    body: SetSlaBody,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    t = await SlaService(session).set_sla(
        task_id, target_seconds=body.target_seconds, working_days_only=body.working_days_only,
    )
    return {
        "id": str(t.id),
        "slaTargetSeconds": t.sla_target_seconds,
        "slaWorkingDaysOnly": t.sla_working_days_only,
        "slaStartedAt": t.sla_started_at.isoformat() if t.sla_started_at else None,
        "slaBreached": t.sla_breached,
        "elapsedSeconds": elapsed_seconds(t),
        "isBreachedNow": is_breached(t),
    }
