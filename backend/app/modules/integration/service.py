"""Integration hub service — the outbox dispatcher and inbound webhook handler (arch §10.2).

Dispatch is idempotent: only outbox events with dispatched_at IS NULL are processed, and each is
marked dispatched once its adapters have been called. Inbound messages are deduplicated by
(system, source_id).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.errors import ConflictError
from app.modules.integration.adapters import ROUTES, deliver
from app.modules.integration.constants import Direction, IntegrationStatus
from app.modules.integration.models import IntegrationLog
from app.modules.integration.repository import IntegrationRepository

logger = logging.getLogger("pgr.integration")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _backoff_seconds(attempts: int) -> int:
    # Exponential backoff, capped: 2, 4, 8, 16, ... up to 5 min.
    return min(2 ** attempts, 300)


class IntegrationService:
    def __init__(self, repo: IntegrationRepository) -> None:
        self.repo = repo
        self.session = repo.session

    async def dispatch_pending(self) -> dict:
        settings = get_settings()
        events = await self.repo.pending_outbox()
        dispatched = 0
        outbound = 0
        failed = 0
        dead = 0
        for ev in events:
            adapters = ROUTES.get(ev.event_type, [])
            if not adapters:
                self.repo.add(IntegrationLog(
                    direction=Direction.outbound, system="internal", event_type=ev.event_type,
                    aggregate_type=ev.aggregate_type, aggregate_id=ev.aggregate_id,
                    status=IntegrationStatus.skipped, detail={"note": "no external route"}, created_at=_now(),
                ))
                ev.dispatched_at = _now()
                dispatched += 1
                continue
            try:
                for adapter in adapters:
                    message = await deliver(adapter, ev.event_type, ev.payload or {})
                    self.repo.add(IntegrationLog(
                        direction=Direction.outbound, system=adapter.system, event_type=ev.event_type,
                        aggregate_type=ev.aggregate_type, aggregate_id=ev.aggregate_id,
                        status=IntegrationStatus.success, detail=message, created_at=_now(),
                    ))
                    outbound += 1
                ev.dispatched_at = _now()
                ev.last_error = None
                dispatched += 1
            except Exception as exc:  # delivery failed — retry with backoff, then dead-letter
                ev.attempts = (ev.attempts or 0) + 1
                ev.last_error = str(exc)[:300]
                self.repo.add(IntegrationLog(
                    direction=Direction.outbound, system="integration", event_type=ev.event_type,
                    aggregate_type=ev.aggregate_type, aggregate_id=ev.aggregate_id,
                    status=IntegrationStatus.failed,
                    detail={"attempt": ev.attempts, "error": ev.last_error}, created_at=_now(),
                ))
                if ev.attempts >= settings.outbox_max_attempts:
                    ev.dead_lettered = True
                    dead += 1
                    logger.error("outbox event %s dead-lettered after %s attempts", ev.id, ev.attempts)
                else:
                    ev.next_attempt_at = _now() + timedelta(seconds=_backoff_seconds(ev.attempts))
                    failed += 1
        await self.session.commit()
        return {"dispatched": dispatched, "outboundCalls": outbound, "failed": failed, "deadLettered": dead}

    async def replay_dead_letter(self, event_id) -> bool:
        """Reset a dead-lettered event so the next dispatch retries it (arch §10.2 reconciliation)."""
        ev = await self.repo.get_outbox_event(event_id)
        if ev is None or not ev.dead_lettered:
            return False
        ev.dead_lettered = False
        ev.attempts = 0
        ev.next_attempt_at = None
        ev.last_error = None
        await self.session.commit()
        return True

    async def handle_inbound(self, system: str, source_id: str, event_type: str, payload: dict) -> dict:
        # Idempotency: ignore repeats of an already-processed source id (arch §10.2).
        if await self.repo.inbound_exists(system, source_id):
            return {"status": "duplicate", "sourceId": source_id}
        try:
            self.repo.add(IntegrationLog(
                direction=Direction.inbound, system=system, event_type=event_type,
                source_id=source_id, status=IntegrationStatus.success, detail=payload, created_at=_now(),
            ))
            await self.session.commit()
        except Exception as exc:  # unique (system, source_id) race
            await self.session.rollback()
            raise ConflictError("Duplicate inbound message") from exc
        return {"status": "processed", "sourceId": source_id}

    async def recent_logs(self, limit: int = 50):
        return await self.repo.recent_logs(limit)

    async def pending_count(self) -> int:
        return await self.repo.pending_count()
