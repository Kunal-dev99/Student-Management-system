"""Notification preferences + unread count for the notification centre (arch §10.4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_principal
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.notifications.service import NotificationService
from app.modules.workflow.constants import NotificationStatus
from app.modules.workflow.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


class PreferenceIn(BaseModel):
    emailEnabled: bool = True
    digest: bool = False
    mutedEvents: list[str] = []


@router.get("/unread-count", summary="Unread notification count for the bell")
async def unread_count(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    n = (await session.execute(
        select(func.count()).select_from(Notification).where(
            Notification.recipient_user_id == principal.user_id,
            Notification.status.in_([NotificationStatus.queued, NotificationStatus.sent]),
        )
    )).scalar_one()
    return {"unread": int(n)}


@router.get("/preferences", summary="My notification preferences")
async def get_preferences(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    return await NotificationService(session).get_or_default(principal.user_id)


@router.put("/preferences", summary="Update my notification preferences")
async def update_preferences(
    body: PreferenceIn,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    return await NotificationService(session).update(
        principal.user_id,
        email_enabled=body.emailEnabled, digest=body.digest, muted_events=body.mutedEvents,
    )
