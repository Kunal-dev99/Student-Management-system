"""Weekly review queue endpoints.

`GET /reviews/weekly` returns the full queue in one JSON payload — the simple, cacheable
form the UI falls back to if streaming misbehaves.

`GET /reviews/weekly/stream` streams a reasoning trace (SSE) and finishes with the same
payload. The frontend renders the trace live so the reveal is paced by real server work,
not by a fake spinner.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from dataclasses import asdict as _asdict

from app.ai.rank import rank as ai_rank
from app.ai.trace import TraceEmitter
from app.core.database import SessionFactory
from app.core.dependencies import require_permission
from app.core.llm.provider import provider_is_live
from app.db.session import get_session
from app.modules.reviews.service import (
    _to_candidates,
    build_candidates,
    weekly_queue,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _serialise(queue) -> dict:
    return {
        "picks": [p.model_dump() for p in queue.picks.picks],
        "provenance": queue.picks.provenance.model_dump(),
        "candidates": [asdict(r) for r in queue.candidates],
        "modelLive": provider_is_live(),
    }


@router.get("/weekly")
async def weekly(
    top_n: int = 5,
    _=Depends(require_permission("student.read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """One-shot payload. Used by clients that don't stream."""
    queue = await weekly_queue(session, top_n=top_n)
    return _serialise(queue)


@router.get("/weekly/stream")
async def weekly_stream(
    top_n: int = 5,
    _=Depends(require_permission("student.read")),
) -> StreamingResponse:
    """SSE — trace steps as they happen, then the final payload.

    The background task opens its OWN session — the request-scoped session from
    Depends(get_session) is torn down as soon as the endpoint returns the
    StreamingResponse, so reusing it from the task raises
    "another operation is in progress" once the pool tries to reuse the connection.
    """
    trace = TraceEmitter()

    async def run() -> None:
        try:
            async with SessionFactory() as session:
                await trace.step(
                    "Fetching the student roster",
                    "active students, milestones, funding arrangements",
                    icon="database",
                )
                rows = await build_candidates(session)

                await trace.step(
                    f"Weighing risk for {len(rows)} students",
                    "overdue work, funding gaps, expected end dates",
                    icon="calculator",
                )

                if not rows:
                    await trace.result({
                        "picks": [],
                        "provenance": {"source": "fallback", "reason": "no candidates"},
                        "candidates": [],
                        "modelLive": provider_is_live(),
                    })
                    return

                # Ship the evidence table + a deterministic fallback pick set NOW, so the
                # UI paints the whole page in ~300ms. The model call keeps running; when
                # it lands we emit a `result` and the UI swaps the picks over.
                shortlist = rows[:10]
                candidates_payload = [_asdict(r) for r in rows]
                provisional = {
                    "picks": [
                        {"id": r.student_id,
                         "reasoning": f"Flagged by: {', '.join(r.reasons[:2])}."}
                        for r in shortlist[:top_n]
                    ],
                    "provenance": {"source": "fallback", "model": None,
                                   "latency_ms": None, "reason": "waiting for model"},
                    "candidates": candidates_payload,
                    "modelLive": provider_is_live(),
                }
                await trace.partial(provisional)

                if provider_is_live():
                    await trace.step(
                        "Waking the model",
                        "handing over the shortlist and the question",
                        icon="sparkles",
                    )
                else:
                    await trace.step(
                        "Choosing priorities offline",
                        "model unavailable — using rule-based ordering",
                        icon="sparkles",
                    )

                picks = await ai_rank(
                    question=(
                        "Which students need a supervisor review this week? Pick the ones "
                        "whose risk flags most warrant attention now."
                    ),
                    candidates=_to_candidates(shortlist),
                    top_n=top_n,
                )

                await trace.step(
                    "Writing the reasoning",
                    "one sentence per pick, grounded in the risk flags",
                    icon="pen",
                )
                await trace.step(
                    "Laying it out beside the evidence",
                    "picks left, deterministic table right",
                    icon="layout",
                )
                await trace.result({
                    "picks": [p.model_dump() for p in picks.picks],
                    "provenance": picks.provenance.model_dump(),
                    "candidates": candidates_payload,
                    "modelLive": provider_is_live(),
                })
        except Exception as exc:  # noqa: BLE001 — surface as a clean error frame
            log.exception("weekly_stream failed")
            await trace.error(str(exc))

    task = asyncio.create_task(run())

    async def emit():
        try:
            async for chunk in trace.stream():
                yield chunk
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(emit(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })
