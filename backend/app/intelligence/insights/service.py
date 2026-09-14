"""Case Insights service — structured LLM synthesis, degrades to deterministic bullets.

Produces:
  * situation:      one grounded sentence describing where this student is right now
  * observations:   2-4 cross-signal patterns the model noticed (never causal claims)
  * suggested_next: 2-4 concrete next steps drawn from the allow-listed action set

Every observation and suggestion is a plain string. The frontend renders them as
bullets. When the LLM is unavailable, we synthesise the same shape from the twin
snapshot deterministically — the UI stays populated.
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal
from app.intelligence.ai_bridge import intelligence_read
from app.intelligence.twin.builder import TwinBuilder


class CaseInsights(BaseModel):
    situation: str = Field(description="One sentence — where this student is right now, grounded in the facts.")
    observations: list[str] = Field(description="2-4 cross-signal observations. Never causal claims.")
    suggested_next: list[str] = Field(description="2-4 concrete next steps (allow-listed action types).")


class InsightsResult(BaseModel):
    student_id: uuid.UUID
    engine_used: str
    situation: str
    observations: list[str]
    suggested_next: list[str]


class CaseInsightsService:
    def __init__(self, session: AsyncSession, principal: Principal) -> None:
        self.session = session
        self.principal = principal

    async def compute(self, student_id: uuid.UUID) -> InsightsResult:
        twin = await TwinBuilder(self.session, self.principal).snapshot(student_id)

        # Compact prompt text — the LLM never sees raw ORM rows.
        pressures = "; ".join(
            f"{p.kind}: {p.label}" for p in twin.pressure_points[:6]
        ) or "no material pressure"
        signals = "; ".join(
            f"{s.target} {s.probability:.0%}" for s in twin.model_signals[:4]
        ) or "no live model scores"
        state = twin.state or {}
        text = (
            f"Student ref: {state.get('student_ref')}\n"
            f"Status: {state.get('status')}\n"
            f"Study mode: {state.get('study_mode')}\n"
            f"Expected end: {state.get('expected_end_date')}\n"
            f"Pressure points (weighted): {pressures}\n"
            f"Model signals: {signals}\n"
            f"Missing sources: {', '.join(twin.blockers) or 'none'}\n"
        )
        result = await intelligence_read(
            feature="case_insights",
            text=text,
            schema=CaseInsights,
            hint=(
                "Synthesise a case snapshot. observations should tie signals together "
                "(e.g. 'engagement and funding weakened in the same window') without "
                "claiming causation. suggested_next should be concrete steps drawn from: "
                "supervisor check-in, funding review, evidence review, reassessment, "
                "or a follow-up task."
            ),
            principal_id=self.principal.user_id,
        )

        if not result.needs_manual:
            return InsightsResult(
                student_id=student_id,
                engine_used=(result.provenance.model or "model"),
                situation=str(result.fields.get("situation") or ""),
                observations=list(result.fields.get("observations") or []),
                suggested_next=list(result.fields.get("suggested_next") or []),
            )

        # Deterministic fallback — same shape, populated from the twin.
        return _fallback_insights(student_id, twin)


def _fallback_insights(student_id: uuid.UUID, twin) -> InsightsResult:
    state = twin.state or {}
    top = twin.pressure_points[0] if twin.pressure_points else None
    situation = (
        f"Student {state.get('student_ref')} is {state.get('status')}"
        f" with {len(twin.pressure_points)} pressure point(s)."
    )
    observations: list[str] = []
    for p in twin.pressure_points[:3]:
        observations.append(f"{p.kind.replace('_', ' ')}: {p.label} (weight {p.weight})")
    if not observations:
        observations = ["No material pressure detected."]

    suggestions: list[str] = []
    kinds = {p.kind for p in twin.pressure_points}
    if "supervision_gap" in kinds:      suggestions.append("Prepare a supervisor check-in brief.")
    if kinds & {"funding_expiring", "no_active_funding"}: suggestions.append("Request a funding review.")
    if kinds & {"milestone_due", "milestone_overdue"}:    suggestions.append("Open an evidence review for the next milestone.")
    if not suggestions:
        suggestions.append(f"Schedule a reassessment for {state.get('student_ref')}.")

    return InsightsResult(
        student_id=student_id,
        engine_used="fallback_rules",
        situation=situation,
        observations=observations,
        suggested_next=suggestions,
    )
