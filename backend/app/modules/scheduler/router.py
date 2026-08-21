"""Scheduler HTTP endpoint (arch §9.3 — worker stand-in)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_session
from app.modules.scheduler.service import SchedulerService

router = APIRouter(prefix="/admin/scheduled-jobs", tags=["scheduler"])


@router.post("/run", summary="Run the periodic scheduled jobs once")
async def run_jobs(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await SchedulerService(session).run_all()
