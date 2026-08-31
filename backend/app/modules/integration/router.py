"""Integration HTTP endpoints (arch §10, §11.5)."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import require_permission
from app.core.errors import AuthError, ValidationAppError
from app.db.session import get_session
from app.modules.integration.repository import IntegrationRepository
from app.modules.integration.schemas import (
    DeadLetterOut,
    DispatchResult,
    IntegrationLogOut,
    IntegrationOverview,
)
from app.modules.integration.service import IntegrationService

router = APIRouter(prefix="/integration", tags=["integration"])


def _svc(session: AsyncSession) -> IntegrationService:
    return IntegrationService(IntegrationRepository(session))


@router.post("/dispatch", response_model=DispatchResult, summary="Dispatch pending outbox events")
async def dispatch(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> DispatchResult:
    # Manual/endpoint trigger stands in for the dispatcher worker until the worker tier lands.
    return DispatchResult.model_validate(await _svc(session).dispatch_pending())


@router.get("/logs", response_model=IntegrationOverview, summary="Integration log + pending count")
async def logs(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> IntegrationOverview:
    svc = _svc(session)
    rows = await svc.recent_logs(50)
    dead = await svc.repo.dead_lettered(50)
    return IntegrationOverview(
        pending=await svc.pending_count(),
        dead_letter_count=await svc.repo.dead_letter_count(),
        logs=[IntegrationLogOut.model_validate(r) for r in rows],
        dead_letters=[DeadLetterOut.model_validate(d) for d in dead],
    )


@router.get("/reconciliation", summary="Is the integration boundary healthy, and what needs a human?")
async def reconciliation(
    windowDays: int = 30,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await _svc(session).reconciliation(window_days=windowDays)


@router.post("/dead-letters/{event_id}/replay", summary="Replay a dead-lettered event")
async def replay_dead_letter(
    event_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    ok = await _svc(session).replay_dead_letter(event_id)
    return {"data": {"replayed": ok}}


class _BulkReplayBody(BaseModel):
    ids: list[uuid.UUID]


@router.post("/dead-letters/replay", summary="F5 — replay many dead-letters in one action")
async def replay_dead_letters_bulk(
    body: _BulkReplayBody,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    return await _svc(session).replay_dead_letters_bulk(body.ids)


@router.post("/webhooks/{system}", summary="Signed inbound webhook (idempotent by source id)")
async def webhook(system: str, request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    raw = await request.body()
    # Verify HMAC-SHA256 signature over the raw body (arch §17: webhooks verify signatures).
    secret = get_settings().app_secret_key.encode()
    expected = hmac.new(secret, raw, hashlib.sha256).hexdigest()
    provided = request.headers.get("X-Signature", "")
    if not hmac.compare_digest(expected, provided):
        raise AuthError("Invalid webhook signature")
    try:
        body = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise ValidationAppError("Invalid JSON body") from exc
    source_id = body.get("sourceId")
    if not source_id:
        raise ValidationAppError("sourceId is required")
    return await _svc(session).handle_inbound(
        system=system, source_id=str(source_id),
        event_type=body.get("eventType", "unknown"), payload=body.get("payload", {}),
    )
