"""LLM bridge for the intelligence layer.

Every LLM call the intelligence surfaces make routes through this module. Reasons:

  1. **Telemetry**: one row per call in `intelligence_telemetry` — engine used, fallback
     path, latency, schema validity. Written on a fresh session so a failing telemetry
     write cannot break the caller's transaction.
  2. **Fallback is first-class**: every function returns a value even when the LLM is
     off. app/ai already provides deterministic fallbacks — we just add telemetry.
  3. **Feature attribution**: callers pass a `feature` name (assistant, twin, change_radar,
     policy_compiler, engagement) so cost/latency dashboards can split by producer.

The bridge deliberately does not expose the raw Groq client — every use flows through
one of the four typed shapes (classify/rank/read/narrate) or their intelligence-flavoured
wrappers below.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from app.ai import classify as ai_classify
from app.ai import narrate as ai_narrate
from app.ai import read as ai_read
from app.ai.types import ClassifyResult, Evidence, Narration, ReadResult
from app.core.database import SessionFactory
from app.intelligence.models import IntelligenceTelemetry
from app.intelligence.schemas import TelemetryEvent

logger = logging.getLogger("pgr.intelligence.bridge")


def _clip(value: str | None, limit: int) -> str | None:
    """Defensive truncation so a long provider error/model name can never crash the
    telemetry insert (columns are sized generously — see migration
    ai_p1_widen_telemetry_cols — this is the belt-and-suspenders backstop for
    whatever they aren't sized for next)."""
    if value is None:
        return None
    return value if len(value) <= limit else value[: limit - 1] + "…"


async def _write_telemetry(event: TelemetryEvent) -> None:
    """Persist telemetry on a dedicated session so failures never leak into the caller."""
    try:
        async with SessionFactory() as s:
            s.add(IntelligenceTelemetry(
                call_class=event.call_class,
                feature=_clip(event.feature, 80) or "unknown",
                engine_used=_clip(event.engine_used, 120) or "unknown",
                fallback_path=_clip(event.fallback_path, 500),
                prompt_template_version=_clip(event.prompt_template_version, 40),
                latency_ms=event.latency_ms,
                tokens_in=event.tokens_in,
                tokens_out=event.tokens_out,
                cost_estimate_usd=event.cost_estimate_usd,
                schema_ok=event.schema_ok,
                request_id=event.request_id,
                principal_id=event.principal_id,
            ))
            await s.commit()
    except Exception:  # noqa: BLE001 — telemetry must never break requests
        logger.exception("intelligence telemetry write failed")


def _engine_from(provenance) -> tuple[str, str | None]:
    """Turn app/ai's `Provenance` into (engine_used, fallback_path)."""
    if provenance.source == "model":
        return (provenance.model or "groq_unknown", None)
    return ("fallback_rules", provenance.reason or "fallback")


# ---------- classify -------------------------------------------------------

async def intelligence_classify(
    *, feature: str, text: str, labels: list[str],
    keyword_rules: dict[str, list[str]] | None = None,
    fallback_label: str | None = None, context: str | None = None,
    principal_id: uuid.UUID | None = None,
) -> ClassifyResult:
    t0 = time.perf_counter()
    result = await ai_classify.classify(
        text=text, labels=labels,
        keyword_rules=keyword_rules, fallback_label=fallback_label, context=context,
    )
    latency = int((time.perf_counter() - t0) * 1000)
    engine, fb = _engine_from(result.provenance)
    await _write_telemetry(TelemetryEvent(
        call_class="classify", feature=feature,
        engine_used=engine, fallback_path=fb,
        prompt_template_version="classify.v1",
        latency_ms=latency, schema_ok=True, principal_id=principal_id,
    ))
    return result


# ---------- narrate --------------------------------------------------------

async def intelligence_narrate(
    *, feature: str, evidence: Evidence, question: str, fallback_template: str,
    principal_id: uuid.UUID | None = None,
) -> Narration:
    t0 = time.perf_counter()
    result = await ai_narrate.narrate(
        evidence=evidence, question=question, fallback_template=fallback_template,
    )
    latency = int((time.perf_counter() - t0) * 1000)
    engine, fb = _engine_from(result.provenance)
    await _write_telemetry(TelemetryEvent(
        call_class="narrate", feature=feature,
        engine_used=engine, fallback_path=fb,
        prompt_template_version="narrate.v1",
        latency_ms=latency, schema_ok=True, principal_id=principal_id,
    ))
    return result


# ---------- read (structured extraction) -----------------------------------

async def intelligence_read(
    *, feature: str, text: str, schema, hint: str | None = None,
    principal_id: uuid.UUID | None = None,
) -> ReadResult:
    """Structured extraction — schema is a Pydantic model class."""
    t0 = time.perf_counter()
    result = await ai_read.read(text=text, schema=schema, hint=hint)
    latency = int((time.perf_counter() - t0) * 1000)
    engine, fb = _engine_from(result.provenance)
    await _write_telemetry(TelemetryEvent(
        call_class="read", feature=feature,
        engine_used=engine, fallback_path=fb,
        prompt_template_version="read.v1",
        latency_ms=latency,
        schema_ok=(not result.needs_manual),
        principal_id=principal_id,
    ))
    return result
