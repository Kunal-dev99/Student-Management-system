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
from app.db.session import get_read_session
from app.modules.assistant.constants import ASSISTANT_PERMISSION, BLOCKED_ACTIONS
from app.modules.assistant.service import AssistantService

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantQuery(BaseModel):
    query: str = Field(..., max_length=2000)
    history: list[dict] | None = None


@router.post("/query", summary="Ask the assistant (read-only)")
async def ask(
    body: AssistantQuery,
    session: AsyncSession = Depends(get_read_session),
    principal: Principal = Depends(require_permission(ASSISTANT_PERMISSION)),
) -> dict:
    return await AssistantService(session, principal).query(body.query, body.history)


@router.get("/capabilities", summary="What the assistant can and cannot do")
async def capabilities(
    _=Depends(require_permission(ASSISTANT_PERMISSION)),
) -> dict:
    return {
        "readOnly": True,
        "examples": [
            "Which students have no supervision meeting in 90 days?",
            "Students with funding expiring in the next 6 months",
            "What's the state of Tom Fisher?",
            "Who is at risk?",
            "my tasks",
            "go to funding",
        ],
        # Surfaced so the UI can explain the boundary rather than failing silently.
        "blockedActions": BLOCKED_ACTIONS,
    }
