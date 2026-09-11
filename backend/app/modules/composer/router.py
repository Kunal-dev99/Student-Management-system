"""Composer HTTP endpoints."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("pgr.composer")


def _sse(event: str, data: dict) -> str:
    """One server-sent event. The blank line terminates the frame."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

from app.core.dependencies import require_permission
from app.core.errors import ValidationAppError
from app.core.llm.governance import check_enabled
from app.core.llm.provider import provider_is_live
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.composer import functions as fx
from app.modules.composer.models import ComposerRun
from app.modules.composer.service import ComposerRefused, ComposerService

router = APIRouter(prefix="/composer", tags=["composer"])


def _camel(s: str) -> str:
    head, *rest = s.split("_")
    return head + "".join(w.title() for w in rest)


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True)


class ComposeRequest(_Camel):
    question: str = Field(min_length=3, max_length=500)
    # Set when the ask came from a saved template rather than free text.
    composition_key: str | None = None


@router.get("/status", summary="Is the composer usable, and what can this caller ask about?")
async def status(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> dict:
    gate = await check_enabled(session)
    return {
        "enabled": gate.allowed,
        "reason": gate.reason,
        "providerLive": provider_is_live(),
        "functions": [
            {"name": f.name, "description": f.description}
            for f in fx.available_to(principal)
        ],
    }


@router.post("", summary="Compose a dashboard from a question")
async def compose(
    body: ComposeRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> dict:
    try:
        result = await ComposerService(session, principal).compose(
            body.question, composition_key=body.composition_key
        )
    except ComposerRefused as exc:
        # A refusal is an expected outcome with a user-facing reason, not a server fault.
        raise ValidationAppError(str(exc)) from exc

    return {
        "composition": result.composition,
        "meta": {
            "functionsCalled": result.functions_called,
            "tokensIn": result.tokens_in,
            "tokensOut": result.tokens_out,
            "latencyMs": result.latency_ms,
            "provider": result.model,
        },
    }


@router.post("/stream", summary="Compose, streaming progress as the work happens")
async def compose_stream(
    body: ComposeRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> StreamingResponse:
    """Server-sent events.

    Composition takes two or three sequential model round-trips. Rather than hold a blank
    spinner for the duration, each real step is emitted as it completes: which data is
    being fetched, what came back, and when layout begins. The final `composition` event
    carries the same payload the non-streaming endpoint returns.
    """

    async def events() -> AsyncIterator[str]:
        service = ComposerService(session, principal)
        try:
            async for progress in service.compose_stream(
                body.question, composition_key=body.composition_key
            ):
                yield _sse(progress.kind, {"message": progress.message, **(progress.data or {})})
        except ComposerRefused as exc:
            yield _sse("error", {"message": str(exc)})
        except Exception:  # pragma: no cover - the stream must always terminate
            # An uncaught exception mid-stream leaves the user with nothing on screen.
            # If the service made any progress at all, emit the deterministic fallback so
            # they see the data that was gathered before the crash; otherwise say so
            # clearly and move on. The audit row keeps the traceback.
            logger.exception("composer stream failed")
            from app.modules.composer.service import _fallback_render
            partial = getattr(service, "_partial_collected", None)
            if partial:
                spec = _fallback_render(body.question, partial, 25)
                yield _sse("composition", {
                    "message": "Done",
                    "composition": spec,
                    "meta": {"functionsCalled": list(
                        {label.split("(")[0] for label in partial}
                    ), "tokensIn": 0, "tokensOut": 0, "latencyMs": 0, "provider": "fallback"},
                })
            else:
                yield _sse("error", {"message": (
                    "I gathered the data but could not lay it out. Try rephrasing the "
                    "question — sometimes a specific ask like 'as a bar chart' or 'for "
                    "the last 12 months' helps."
                )})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            # Proxies that buffer would defeat the point of streaming.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/runs", summary="Recent composer activity (audit)")
async def runs(
    limit: int = 25,
    session: AsyncSession = Depends(get_session),
    _: Principal = Depends(require_permission("audit.read")),
) -> list[dict]:
    rows = (
        await session.execute(
            select(ComposerRun).order_by(desc(ComposerRun.created_at)).limit(min(limit, 100))
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "question": r.question,
            "functionsCalled": r.functions_called or [],
            "provider": r.provider,
            "model": r.model,
            "tokensIn": r.tokens_in,
            "tokensOut": r.tokens_out,
            "latencyMs": r.latency_ms,
            "ok": r.ok,
            "error": r.error,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
