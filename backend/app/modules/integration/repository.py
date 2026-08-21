"""Integration data access (queries only)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integration.models import IntegrationLog
from app.modules.workflow.models import OutboxEvent


class IntegrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def pending_outbox(self, limit: int = 200) -> list[OutboxEvent]:
        # Eligible = undispatched, not dead-lettered, and past its backoff window (arch §10.2).
        now = datetime.now(timezone.utc)
        stmt = (
            select(OutboxEvent)
            .where(
                OutboxEvent.dispatched_at.is_(None),
                OutboxEvent.dead_lettered.is_(False),
                (OutboxEvent.next_attempt_at.is_(None)) | (OutboxEvent.next_attempt_at <= now),
            )
            .order_by(OutboxEvent.created_at)   # ordered delivery (arch §10.2)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def pending_count(self) -> int:
        stmt = select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.dispatched_at.is_(None), OutboxEvent.dead_lettered.is_(False)
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def dead_lettered(self, limit: int = 100) -> list[OutboxEvent]:
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.dead_lettered.is_(True))
            .order_by(OutboxEvent.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def dead_letter_count(self) -> int:
        stmt = select(func.count()).select_from(OutboxEvent).where(OutboxEvent.dead_lettered.is_(True))
        return int((await self.session.execute(stmt)).scalar_one())

    async def get_outbox_event(self, event_id) -> OutboxEvent | None:
        return (await self.session.execute(
            select(OutboxEvent).where(OutboxEvent.id == event_id)
        )).scalar_one_or_none()

    async def inbound_exists(self, system: str, source_id: str) -> bool:
        stmt = select(func.count()).select_from(IntegrationLog).where(
            IntegrationLog.system == system, IntegrationLog.source_id == source_id
        )
        return int((await self.session.execute(stmt)).scalar_one()) > 0

    async def recent_logs(self, limit: int = 50) -> list[IntegrationLog]:
        stmt = select(IntegrationLog).order_by(IntegrationLog.created_at.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    def add(self, obj) -> None:
        self.session.add(obj)
