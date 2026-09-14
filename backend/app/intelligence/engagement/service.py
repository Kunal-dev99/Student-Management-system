"""Engagement trajectory — deterministic event log + rolling snapshot label.

The current single relationship-signal badge becomes a time series. Events are
recorded when supervision facts change; snapshots are computed on demand (and can
be persisted for the trajectory chart).

Rule set (rules engine, no LLM here):
    meeting_logged           → +5
    commitment_completed     → +3
    milestone_decided        → +2
    interval_missed          → -6
    message_exchanged        → +1
    context_override         → +0 (visible in the drivers panel only)

Label thresholds on the 90-day rolling score:
    >= 10   → thriving
    -5..9   → steady
    -15..-6 → drifting
    < -15   → strained
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.ai_bridge import intelligence_classify
from app.intelligence.models_p2 import EngagementEvent, EngagementSnapshot

_ENGAGEMENT_LABELS = ["thriving", "steady", "drifting", "strained"]
_ENGAGEMENT_KEYWORDS: dict[str, list[str]] = {
    "thriving":  ["meeting_logged", "commitment_completed"],
    "drifting":  ["interval_missed"],
    "strained":  ["interval_missed"],
}


EVENT_WEIGHTS: dict[str, int] = {
    "meeting_logged":        5,
    "commitment_completed":  3,
    "milestone_decided":     2,
    "message_exchanged":     1,
    "interval_missed":      -6,
    "context_override":      0,
}


def _label(score: int) -> str:
    if score >= 10:
        return "thriving"
    if score >= -5:
        return "steady"
    if score >= -15:
        return "drifting"
    return "strained"


class EngagementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_event(
        self, student_id: uuid.UUID, kind: str, occurred_at: datetime | None = None,
        reason_code: str | None = None, payload: dict[str, Any] | None = None,
    ) -> EngagementEvent:
        weight = EVENT_WEIGHTS.get(kind, 0)
        row = EngagementEvent(
            student_id=student_id,
            occurred_at=occurred_at or datetime.now(timezone.utc),
            kind=kind,
            weight=weight,
            reason_code=reason_code,
            payload=payload,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def compute_snapshot(self, student_id: uuid.UUID,
                                 window_days: int = 90,
                                 engine: str = "rules") -> EngagementSnapshot:
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        events = (await self.session.execute(
            select(EngagementEvent)
            .where(EngagementEvent.student_id == student_id,
                   EngagementEvent.occurred_at >= cutoff)
        )).scalars().all()

        score = sum(e.weight for e in events)
        drivers = dict(Counter(e.kind for e in events))
        label = _label(score)
        engine_used = "rules"

        # LLM label enrichment: the numeric score is authoritative but the label may
        # be re-picked from a fixed set when a nuanced qualitative call helps.
        # Score, drivers, thresholds are unchanged; deterministic label stays the fallback.
        if engine == "llm":
            summary_lines = [f"Window score: {score}", f"Deterministic label: {label}"]
            for kind, count in drivers.items():
                summary_lines.append(f"- {kind}: {count}")
            classified = await intelligence_classify(
                feature="engagement",
                text="\n".join(summary_lines),
                labels=_ENGAGEMENT_LABELS,
                keyword_rules=_ENGAGEMENT_KEYWORDS,
                fallback_label=label,
                context="Reclassify engagement given the deterministic score + driver mix.",
            )
            label = classified.label
            if classified.provenance.source == "model":
                engine_used = "llm"

        row = EngagementSnapshot(
            student_id=student_id,
            computed_at=datetime.now(timezone.utc),
            label=label,
            score=score,
            drivers=drivers,
            engine=engine_used,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def trajectory(self, student_id: uuid.UUID,
                          limit: int = 24) -> tuple[list[EngagementSnapshot], list[EngagementEvent]]:
        snapshots = (await self.session.execute(
            select(EngagementSnapshot)
            .where(EngagementSnapshot.student_id == student_id)
            .order_by(EngagementSnapshot.computed_at.desc())
            .limit(limit)
        )).scalars().all()
        recent_events = (await self.session.execute(
            select(EngagementEvent)
            .where(EngagementEvent.student_id == student_id)
            .order_by(EngagementEvent.occurred_at.desc())
            .limit(50)
        )).scalars().all()
        return list(reversed(snapshots)), list(recent_events)
