"""Meeting-brief endpoints — JSON and SSE.

`GET /meeting-brief/{student_id}` returns the finished brief.
`GET /meeting-brief/{student_id}/stream` streams the reasoning trace, ships the evidence
early via a `partial` frame, then swaps the paragraph in when the model returns.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict as _asdict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.narrate import narrate as ai_narrate
from app.ai.trace import TraceEmitter
from app.core.database import SessionFactory
from app.core.dependencies import require_permission
from app.core.llm.provider import provider_is_live
from app.db.session import get_session
from app.modules.meeting_brief.service import (
    _fallback_paragraph,
    _suggested_questions,
    _to_evidence_payload,
    build_brief,
    build_evidence,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/meeting-brief", tags=["meeting-brief"])


def _serialise(brief) -> dict:
    ev = brief.evidence
    return {
        "student": {
            "id": ev.student_id,
            "name": ev.student_name,
            "ref": ev.student_ref,
        },
        "lastMeetingOn": ev.last_meeting_on.isoformat() if ev.last_meeting_on else None,
        "lastMeetingActions": ev.last_meeting_actions,
        "daysSinceLast": ev.days_since_last,
        "nextMeetingOn": ev.next_meeting_on.isoformat() if ev.next_meeting_on else None,
        "changes": [_asdict(c) for c in ev.changes],
        "openFlags": ev.open_flags,
        "paragraph": brief.narration.body,
        "provenance": brief.narration.provenance.model_dump(),
        "suggestedQuestions": brief.suggested_questions,
        "modelLive": provider_is_live(),
    }


@router.get("/{student_id}")
async def one_shot(
    student_id: uuid.UUID,
    _=Depends(require_permission("student.read")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        brief = await build_brief(session, student_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _serialise(brief)


@router.get("/{student_id}/stream")
async def stream(
    student_id: uuid.UUID,
    _=Depends(require_permission("student.read")),
) -> StreamingResponse:
    trace = TraceEmitter()

    async def run() -> None:
        try:
            async with SessionFactory() as session:
                await trace.step(
                    "Opening the supervision record",
                    "meetings, milestones, funding, portal signals",
                    icon="database",
                )
                try:
                    ev = await build_evidence(session, student_id)
                except ValueError as exc:
                    await trace.error(str(exc))
                    return

                await trace.step(
                    "Comparing then and now",
                    f"{len(ev.changes)} change(s) since last meeting, {len(ev.open_flags)} open flag(s)",
                    icon="calculator",
                )

                # Ship the evidence + a deterministic paragraph immediately so the page
                # is fully useful in ~300ms. The model call keeps running.
                fallback_body = _fallback_paragraph(ev)
                provisional = {
                    "student": {"id": ev.student_id, "name": ev.student_name, "ref": ev.student_ref},
                    "lastMeetingOn": ev.last_meeting_on.isoformat() if ev.last_meeting_on else None,
                    "lastMeetingActions": ev.last_meeting_actions,
                    "daysSinceLast": ev.days_since_last,
                    "nextMeetingOn": ev.next_meeting_on.isoformat() if ev.next_meeting_on else None,
                    "changes": [_asdict(c) for c in ev.changes],
                    "openFlags": ev.open_flags,
                    "paragraph": fallback_body,
                    "provenance": {"source": "fallback", "model": None,
                                   "latency_ms": None, "reason": "waiting for model"},
                    "suggestedQuestions": _suggested_questions(ev),
                    "modelLive": provider_is_live(),
                }
                await trace.partial(provisional)

                if provider_is_live():
                    await trace.step(
                        "Writing the brief",
                        "one paragraph, grounded in the evidence",
                        icon="pen",
                    )
                else:
                    await trace.step(
                        "Writing the brief offline",
                        "model unavailable — plain summary",
                        icon="pen",
                    )

                evidence_payload = _to_evidence_payload(ev)
                narration = await ai_narrate(
                    evidence=evidence_payload,
                    question=(
                        "Brief a colleague on this student in two to three short sentences, "
                        "warm and specific — the way a fellow supervisor would in a "
                        "staff-room corridor, not how a system report would phrase it.\n"
                        "\n"
                        "Rules:\n"
                        "- Use the student's first name (their full name is in the context).\n"
                        "- Address the reader as 'you' — the supervisor about to walk in.\n"
                        "- Name concrete things that changed. Never say 'N changes have "
                        "  occurred', '0 open flags', or 'primary item requiring attention'.\n"
                        "- If nothing has changed since last time, say that plainly.\n"
                        "- Skip 'open flag' vocabulary — if a flag matters, name it in plain "
                        "  words (e.g. 'their annual review is overdue').\n"
                        "- Do NOT narrate absences ('no pending actions', 'no flags', "
                        "  'nothing else'). If there are no flags, just don't mention flags.\n"
                        "- End with one sentence pointing at what would be most useful to "
                        "  raise first. This closing sentence MUST reference a concrete "
                        "  item already in the evidence — a specific change, agreed action, "
                        "  or open flag by name. Do NOT invent categories like "
                        "  'research plan', 'upcoming milestones', or 'next steps' unless "
                        "  those exact things appear in the evidence.\n"
                        "- If there is nothing specific to point at, close with a general "
                        "  check-in question addressed to the student by first name.\n"
                        "- Under 55 words. Neutral, informational tone."
                    ),
                    fallback_template=fallback_body,
                )

                await trace.step(
                    "Laying it out beside the record",
                    "brief left, evidence right",
                    icon="layout",
                )
                await trace.result({
                    **provisional,
                    "paragraph": narration.body,
                    "provenance": narration.provenance.model_dump(),
                })
        except Exception as exc:  # noqa: BLE001
            log.exception("meeting-brief stream failed")
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
