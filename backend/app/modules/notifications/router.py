"""Notification preferences + unread count for the notification centre (arch §10.4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
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
    # F6 — quiet hours: minutes-since-midnight (0..1439). Nulls disable the quiet window.
    quietStart: int | None = None
    quietEnd: int | None = None


class BouncePayload(BaseModel):
    email: str
    bounceType: str = "hard"        # 'hard' | 'soft' | 'complaint'
    reason: str | None = None


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
        quiet_start=body.quietStart, quiet_end=body.quietEnd,
    )


# ---------------- F6 — email bounce webhook + quiet-hours + digest ----------------

@router.post("/webhooks/email/bounce", summary="F6 — provider bounce hook (deactivates on hard bounce)")
async def email_bounce(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Public webhook — the provider (SES / Mailgun / SMTP relay) posts here. Hard bounces
    deactivate email for the affected user; soft bounces are recorded but leave email on.

    Signed like every other webhook (``X-Signature``), so nobody can switch off a user's email
    with a fake bounce. The email provider is one account for the whole platform, so a bounce
    isn't tied to an institution: on a single shared address it is applied in every institution
    where that address belongs to a user or person (found by a narrow lookup that returns only
    institution ids), each in its own scope. On an institution's subdomain, only that one."""
    import json

    from app.core import pre_auth
    from app.core.errors import ValidationAppError
    from app.core.inbound import verified_inbound
    from app.core.tenant_context import tenant_scope
    from app.core.tenant_resolver import tenant_for_request

    tid, raw = await verified_inbound(request)
    try:
        body = BouncePayload.model_validate(json.loads(raw or b"{}"))
    except ValueError as exc:
        raise ValidationAppError("Invalid bounce payload") from exc

    host_tid = await tenant_for_request(request)
    if host_tid is not None:
        tenants = [host_tid]
    else:
        tenants = await pre_auth.tenants_with_email(session, body.email)
        await session.rollback()   # end the lookup; each institution below gets its own transaction
    deactivated = False
    for t in tenants or [tid]:     # an unknown address is still recorded, for the platform
        async with tenant_scope(t):
            deactivated = await _record_bounce(session, body) or deactivated
    return {"recorded": True, "emailChannelDeactivated": deactivated}


async def _record_bounce(session: AsyncSession, body: "BouncePayload") -> bool:
    """Record the bounce in the acting institution; switch off email for a hard bounce."""
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.modules.identity.models import User
    from app.modules.notifications.models import EmailBounce, NotificationPreference
    from app.modules.person.models import Person

    person = (await session.execute(
        select(Person).where(Person.email == body.email)
    )).scalar_one_or_none()

    row = EmailBounce(
        person_id=person.id if person else None,
        email=body.email, bounce_type=body.bounceType,
        reason=body.reason, received_at=datetime.now(timezone.utc),
    )
    session.add(row)

    deactivated = False
    if body.bounceType in ("hard", "complaint"):
        user = (await session.execute(
            select(User).where(User.email == body.email)
        )).scalar_one_or_none()
        if user is not None:
            pref = (await session.execute(
                select(NotificationPreference).where(NotificationPreference.user_id == user.id)
            )).scalar_one_or_none()
            if pref is None:
                pref = NotificationPreference(user_id=user.id, email_enabled=False)
                session.add(pref)
            else:
                pref.email_enabled = False
            deactivated = True

    await session.commit()
    return deactivated
