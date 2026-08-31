"""F6 — Assistant write-intent endpoints (propose → confirm → execute)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.errors import ConflictError, NotFoundError, WorkflowError
from app.db.session import get_session
from app.modules.assistant.constants import BLOCKED_ACTIONS
from app.modules.assistant.f6_models import AssistantWriteIntent


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ProposeBody(_Camel):
    action: str
    scope: dict
    preview: dict


router = APIRouter(prefix="/assistant/intents", tags=["assistant"])


@router.post("", status_code=201, summary="F6 — propose a write; returns intent id for confirmation")
async def propose(
    body: ProposeBody,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("assistant.use")),
) -> dict:
    if body.action in BLOCKED_ACTIONS:
        raise WorkflowError(
            f"Action '{body.action}' is on the Tier-3 blocked list: {BLOCKED_ACTIONS[body.action]}"
        )
    row = AssistantWriteIntent(
        proposed_by_user_id=principal.user_id,
        action=body.action, scope=body.scope, preview=body.preview,
        state="proposed",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {
        "id": str(row.id), "action": row.action, "state": row.state,
        "preview": row.preview,
    }


@router.post("/{intent_id}/execute", summary="F6 — user confirms and the write runs")
async def execute(
    intent_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    principal=Depends(require_permission("assistant.use")),
) -> dict:
    row = (await session.execute(
        select(AssistantWriteIntent).where(AssistantWriteIntent.id == intent_id)
    )).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Intent not found")
    if row.state != "proposed":
        raise ConflictError(f"Intent already {row.state}")

    # Dispatch. Only 'meeting.log' is wired in F6 as a proof of the pattern; other actions can
    # be added one at a time as they are signed off. Everything on BLOCKED_ACTIONS is refused
    # at propose time above, so this switch only sees safely-listed actions.
    if row.action == "meeting.log":
        # A trivial, side-effect-free demo: mark the intent as executed with a note.
        # A real implementation would call MeetingService.log(...) here.
        row.outcome = "meeting.log accepted (F6 stub — wire the real service call next)"
    else:
        row.state = "failed"
        row.outcome = f"F6 has no handler for action '{row.action}' yet"
        await session.commit()
        return {"id": str(row.id), "state": row.state, "outcome": row.outcome}

    row.state = "executed"
    row.confirmed_at = datetime.now(timezone.utc)
    row.executed_at = row.confirmed_at
    await session.commit()
    return {"id": str(row.id), "state": row.state, "outcome": row.outcome}


@router.post("/{intent_id}/cancel", summary="F6 — cancel a proposed intent")
async def cancel(
    intent_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("assistant.use")),
) -> dict:
    row = (await session.execute(
        select(AssistantWriteIntent).where(AssistantWriteIntent.id == intent_id)
    )).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Intent not found")
    if row.state != "proposed":
        raise ConflictError(f"Intent already {row.state}")
    row.state = "cancelled"
    await session.commit()
    return {"id": str(row.id), "state": row.state}
