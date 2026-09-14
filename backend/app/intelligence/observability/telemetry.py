"""One-row-per-call AI telemetry writer.

Deliberately fire-and-forget: telemetry never fails the request that produced it. A
telemetry write error is swallowed and logged — the user's answer must not be blocked
by an observability side-effect.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.models import IntelligenceTelemetry
from app.intelligence.schemas import TelemetryEvent

logger = logging.getLogger("pgr.intelligence.telemetry")


class TelemetryLogger:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(self, event: TelemetryEvent) -> None:
        try:
            self.session.add(IntelligenceTelemetry(
                call_class=event.call_class,
                feature=event.feature,
                engine_used=event.engine_used,
                fallback_path=event.fallback_path,
                prompt_template_version=event.prompt_template_version,
                latency_ms=event.latency_ms,
                tokens_in=event.tokens_in,
                tokens_out=event.tokens_out,
                cost_estimate_usd=event.cost_estimate_usd,
                schema_ok=event.schema_ok,
                request_id=event.request_id,
                principal_id=event.principal_id,
            ))
            await self.session.flush()
        except Exception:  # noqa: BLE001 — telemetry must never break requests
            logger.exception("Failed to write intelligence telemetry")
