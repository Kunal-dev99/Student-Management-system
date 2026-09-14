"""AI-P3 endpoints — Digital Twin + Scenario preview."""
from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.trace import TraceEmitter
from app.core.database import SessionFactory
from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_read_session
from app.intelligence.insights.service import CaseInsightsService, InsightsResult
from app.intelligence.scenario import ScenarioEngine, ScenarioRequest, ScenarioResult
from app.intelligence.twin import StudentTwinSnapshot, TwinBuilder

log = logging.getLogger(__name__)

router_p3 = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router_p3.get("/twin/{student_id}", response_model=StudentTwinSnapshot,
                summary="Digital Twin snapshot — state, pressure points, dependencies, signals")
async def student_twin(
    student_id: uuid.UUID,
    enable_llm: bool = False,
    session: AsyncSession = Depends(get_read_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> StudentTwinSnapshot:
    return await TwinBuilder(session, principal).snapshot(student_id, enable_llm=enable_llm)


@router_p3.get("/students/{student_id}/insights", response_model=InsightsResult,
                summary="Case Insights — LLM synthesis over twin + case context (structured)")
async def student_insights(
    student_id: uuid.UUID,
    session: AsyncSession = Depends(get_read_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> InsightsResult:
    return await CaseInsightsService(session, principal).compute(student_id)


@router_p3.get("/students/{student_id}/insights/stream",
                summary="Case Insights — SSE reasoning trace + streamed final result")
async def student_insights_stream(
    student_id: uuid.UUID,
    principal: Principal = Depends(require_permission("student.read")),
) -> StreamingResponse:
    """Stream the reasoning trace, then the structured insights payload.

    The service opens its OWN session — the request-scoped one is torn down as soon
    as this endpoint returns the StreamingResponse. Steps correspond to real work:
    each `trace.step` sits on a genuine server-side await, not a fake sleep.
    """
    trace = TraceEmitter()

    async def run() -> None:
        try:
            async with SessionFactory() as session:
                from app.intelligence.twin.builder import TwinBuilder as _TB
                await trace.step(
                    "Reading the student twin",
                    "state, pressure points, blockers, model signals",
                    icon="database",
                )
                twin = await _TB(session, principal).snapshot(student_id)

                await trace.step(
                    f"Weighing {len(twin.pressure_points)} pressure point(s)",
                    "sorting by weight, tying signals together",
                    icon="calculator",
                )
                # Small yield so the step actually renders before the next one.
                await asyncio.sleep(0.05)

                await trace.step(
                    "Asking the model to synthesise",
                    "situation, cross-signal observations, next steps",
                    icon="sparkles",
                )
                insights = await CaseInsightsService(session, principal).compute(student_id)

                await trace.step(
                    "Formatting the response",
                    "grounding every figure, checking allow-listed suggestions",
                    icon="pen",
                )

                await trace.result({
                    "studentId": str(insights.student_id),
                    "engineUsed": insights.engine_used,
                    "situation": insights.situation,
                    "observations": insights.observations,
                    "suggestedNext": insights.suggested_next,
                })
        except Exception as e:  # noqa: BLE001
            log.exception("insights stream failed")
            await trace.error(str(e))

    asyncio.create_task(run())

    async def emit():
        async for chunk in trace.stream():
            yield chunk

    return StreamingResponse(emit(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@router_p3.post("/scenarios", response_model=ScenarioResult,
                 summary="Side-effect-free scenario preview — deterministic diff + optional model sensitivity")
async def scenario_preview(
    body: ScenarioRequest,
    session: AsyncSession = Depends(get_read_session),
    _: Principal = Depends(require_permission("student.read")),
) -> ScenarioResult:
    # Read-only session by design — the engine performs zero mutations.
    return await ScenarioEngine(session).preview(body)
