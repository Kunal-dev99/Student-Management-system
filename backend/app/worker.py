"""Background worker (arch §9.3, §10.2) — the real periodic runner.

Runs three jobs on a schedule instead of waiting for someone to click "Run now":
- scheduled jobs   (milestones due, funding expiring, overdue-task escalation)
- outbox dispatch  (with retry/backoff + dead-letter)
- notification delivery (in-app + best-effort email)

Runs as a separate process alongside the API (`python -m app.worker`), sharing the same code and
database. The manual endpoints (/scheduler/run, /integration/dispatch) still work for tests/demos.

No Docker/broker needed — APScheduler drives it in-process.
"""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.core.logging import configure_logging

logger = logging.getLogger("pgr.worker")


async def _tenant_ids() -> list:
    """Active tenants. The tenant table itself is not tenant-scoped, so no bypass is needed."""
    from sqlalchemy import select

    from app.modules.tenant.models import Tenant

    async with SessionFactory() as session:
        rows = await session.execute(select(Tenant.id).where(Tenant.deactivated_at.is_(None)))
        return [r[0] for r in rows.all()]


async def _per_tenant(label: str, job) -> None:
    """T1 — RLS is fail-closed, so the worker runs each job once per tenant with that tenant
    set: it only sees, and only writes, that tenant's rows (new rows are stamped with it)."""
    from app.core.tenant_context import tenant_scope

    for tid in await _tenant_ids():
        async with tenant_scope(tid):
            try:
                async with SessionFactory() as session:
                    await job(session, tid)
            except Exception:
                logger.exception("worker job %s failed for tenant %s", label, tid)


async def _run_scheduled_jobs() -> None:
    from app.modules.scheduler.service import SchedulerService

    async def job(session, tid):
        result = await SchedulerService(session).run_all()
        logger.info("scheduled jobs ran for tenant %s: %s", tid, result)

    await _per_tenant("scheduled_jobs", job)


async def _run_dispatch() -> None:
    from app.modules.integration.repository import IntegrationRepository
    from app.modules.integration.service import IntegrationService

    async def job(session, tid):
        result = await IntegrationService(IntegrationRepository(session)).dispatch_pending()
        if result["dispatched"] or result["failed"] or result["deadLettered"]:
            logger.info("outbox dispatch for tenant %s: %s", tid, result)

    await _per_tenant("outbox_dispatch", job)


async def _run_notifications() -> None:
    from app.modules.notifications.service import NotificationService

    async def job(session, tid):
        result = await NotificationService(session).deliver_queued()
        if result["delivered"]:
            logger.info("notifications delivered for tenant %s: %s", tid, result)

    await _per_tenant("notifications", job)


def _guard(coro_fn):
    """Wrap a job so an exception in one tick never kills the scheduler."""
    async def _wrapped():
        try:
            await coro_fn()
        except Exception:
            logger.exception("worker job failed: %s", coro_fn.__name__)
    return _wrapped


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_guard(_run_scheduled_jobs), "interval",
                      seconds=settings.worker_scheduler_interval_seconds, id="scheduled_jobs")
    scheduler.add_job(_guard(_run_dispatch), "interval",
                      seconds=settings.worker_dispatch_interval_seconds, id="outbox_dispatch")
    scheduler.add_job(_guard(_run_notifications), "interval",
                      seconds=settings.worker_notify_interval_seconds, id="notifications")
    scheduler.start()
    logger.info(
        "PGR worker started (scheduled=%ss, dispatch=%ss, notify=%ss). Ctrl+C to stop.",
        settings.worker_scheduler_interval_seconds,
        settings.worker_dispatch_interval_seconds,
        settings.worker_notify_interval_seconds,
    )
    # Run one pass immediately so effects are visible without waiting a full interval.
    await _guard(_run_dispatch)()
    await _guard(_run_notifications)()
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):  # pragma: no cover
        logger.info("PGR worker stopping.")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
