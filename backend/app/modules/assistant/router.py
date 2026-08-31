"""Assistant endpoints (Phase 5.1 — read-only, admin pilot).

Guarded by `assistant.use`, which is seeded only to Institution Administrator and PGR
Administrator. Reads route to the replica session like other read paths.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_read_session, get_session
from app.modules.assistant.constants import ASSISTANT_PERMISSION, BLOCKED_ACTIONS
from app.modules.assistant.service import AssistantService

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantQuery(BaseModel):
    query: str = Field(..., max_length=2000)
    history: list[dict] | None = None
    # CB-B — session id enables multi-turn slot memory (pronoun resolution).
    sessionId: str | None = Field(default=None, max_length=100)


class AssistantConfirm(BaseModel):
    pendingId: str = Field(..., max_length=64)


@router.post("/query", summary="Ask the assistant (read or stage-write)")
async def ask(
    body: AssistantQuery,
    session: AsyncSession = Depends(get_session),   # writes need a writable session
    principal: Principal = Depends(require_permission(ASSISTANT_PERMISSION)),
) -> dict:
    return await AssistantService(session, principal).query(
        body.query, body.history, session_id=body.sessionId,
    )


@router.post("/confirm", summary="Execute a previously-staged write intent")
async def confirm(
    body: AssistantConfirm,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission(ASSISTANT_PERMISSION)),
) -> dict:
    return await AssistantService(session, principal).confirm(body.pendingId)


@router.get("/capabilities", summary="What the assistant can and cannot do")
async def capabilities(
    _=Depends(require_permission(ASSISTANT_PERMISSION)),
) -> dict:
    return {
        "readOnly": True,
        "examples": [
            "Which students have no supervision meeting in 90 days?",
            "Held payments this quarter",
            "What's the state of Tom Fisher?",
            "Who is at risk?",
            "my tasks",
            "go to funding",
        ],
        # Surfaced so the UI can explain the boundary rather than failing silently.
        "blockedActions": BLOCKED_ACTIONS,
    }


class TelemetryAssign(BaseModel):
    assignedIntent: str | None = Field(default=None, max_length=120)
    synonymNote: str | None = Field(default=None, max_length=500)


@router.get("/telemetry", summary="Unmatched-query telemetry — vocab review queue")
async def telemetry(
    limit: int = 50,
    unreviewedOnly: bool = True,
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    """CB-C — list redacted unmatched queries so an admin can grow the vocabulary."""
    from sqlalchemy import select
    from app.modules.assistant.telemetry_models import AssistantUnmatchedQuery
    stmt = select(AssistantUnmatchedQuery).order_by(AssistantUnmatchedQuery.created_at.desc())
    if unreviewedOnly:
        stmt = stmt.where(AssistantUnmatchedQuery.reviewed_at.is_(None))
    stmt = stmt.limit(max(1, min(200, limit)))
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "entries": [
            {
                "id": str(r.id),
                "queryRedacted": r.query_redacted,
                "originalLength": r.original_length,
                "sessionRole": r.session_role,
                "suggestedIntents": r.suggested_intents,
                "assignedIntent": r.assigned_intent,
                "synonymNote": r.synonym_note,
                "reviewedAt": r.reviewed_at.isoformat() if r.reviewed_at else None,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.post("/telemetry/{entry_id}/assign", summary="Assign an unmatched query to an intent")
async def telemetry_assign(
    entry_id: str,
    body: TelemetryAssign,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("admin.configure")),
) -> dict:
    """CB-C — record an admin's decision about an unmatched query. A NULL intent means
    'reviewed and not worth adding' — the row is marked reviewed so it drops off the queue."""
    import uuid as _uuid
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.modules.assistant.telemetry_models import AssistantUnmatchedQuery
    row = (await session.execute(
        select(AssistantUnmatchedQuery).where(AssistantUnmatchedQuery.id == _uuid.UUID(entry_id))
    )).scalar_one_or_none()
    if row is None:
        return {"status": "not_found"}
    row.assigned_intent = body.assignedIntent
    row.synonym_note = body.synonymNote
    row.reviewed_at = datetime.now(timezone.utc)
    await session.commit()
    return {"status": "reviewed", "id": str(row.id)}


@router.get("/help", summary="Every intent the assistant knows, grouped by lens")
async def help_surface(
    _=Depends(require_permission(ASSISTANT_PERMISSION)),
) -> dict:
    """CB-A — expose the intent surface so users learn what they can ask."""
    from app.modules.fuzzy.intents import registry
    groups: dict[str, list[dict]] = {}
    for intent in registry().all():
        groups.setdefault(intent.group, []).append({
            "name": intent.name,
            "description": intent.description,
            "examples": list(intent.examples[:3]),
        })
    return {"groups": [{"name": g, "intents": v} for g, v in sorted(groups.items())]}
