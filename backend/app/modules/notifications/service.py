"""Notification delivery + preferences (arch §10.4).

In-app is the primary channel (the notification row itself). Email is a best-effort second
channel, gated by the recipient's preferences. `deliver_queued` is called by the worker each tick
(and by the manual scheduler endpoint) to flush queued notifications.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.email import send_email
from app.modules.identity.models import User
from app.modules.notifications.models import NotificationPreference
from app.modules.workflow.constants import NotificationStatus
from app.modules.workflow.models import Notification

logger = logging.getLogger("pgr.notify")

# template code -> human subject. Body falls back to a generic line + a link into the app.
SUBJECTS = {
    "milestone.decided": "Your progression milestone has a decision",
    "task.assigned": "You have a new task",
    "task.escalated": "A task needs attention",
    "funding.expiring": "Funding arrangement expiring soon",
    "thesis.outcome": "Your thesis examination outcome",
    "supervision.assigned": "You have a new supervisee",
}


def _render(template: str, payload: dict | None) -> tuple[str, str]:
    subject = SUBJECTS.get(template, f"PGR Platform update: {template}")
    base = get_settings().app_base_url
    lines = [subject, ""]
    if payload:
        for k, v in payload.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
    lines.append(f"Sign in to the PGR Platform to view details: {base}")
    return subject, "\n".join(lines)


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _preference(self, user_id: uuid.UUID) -> NotificationPreference | None:
        return (await self.session.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        )).scalar_one_or_none()

    async def get_or_default(self, user_id: uuid.UUID) -> dict:
        pref = await self._preference(user_id)
        if pref is None:
            return {"emailEnabled": True, "digest": False, "mutedEvents": [],
                    "quietStart": None, "quietEnd": None}
        return {
            "emailEnabled": pref.email_enabled, "digest": pref.digest,
            "mutedEvents": pref.muted_events or [],
            "quietStart": pref.quiet_start, "quietEnd": pref.quiet_end,
        }

    async def update(
        self, user_id: uuid.UUID, *, email_enabled: bool, digest: bool, muted_events: list[str],
        quiet_start: int | None = None, quiet_end: int | None = None,
    ) -> dict:
        pref = await self._preference(user_id)
        if pref is None:
            pref = NotificationPreference(user_id=user_id)
            self.session.add(pref)
        pref.email_enabled = email_enabled
        pref.digest = digest
        pref.muted_events = muted_events
        pref.quiet_start = quiet_start
        pref.quiet_end = quiet_end
        await self.session.commit()
        return await self.get_or_default(user_id)

    @staticmethod
    def in_quiet_window(pref: NotificationPreference | None, now: "datetime") -> bool:
        """F6 — is the current time inside the user's quiet-hours window?"""
        if pref is None or pref.quiet_start is None or pref.quiet_end is None:
            return False
        cur = now.hour * 60 + now.minute
        start, end = pref.quiet_start, pref.quiet_end
        if start <= end:
            return start <= cur < end
        # wraps midnight
        return cur >= start or cur < end

    async def deliver_queued(self, limit: int = 200) -> dict:
        """Flush queued notifications: in-app becomes 'sent'; email sent when the user allows it."""
        from app.modules.settings.service import setting_value

        rows = (await self.session.execute(
            select(Notification).where(Notification.status == NotificationStatus.queued).limit(limit)
        )).scalars().all()
        # Phase 8 — the institution kill-switch beats personal preferences: off means in-app
        # only, platform-wide, regardless of what individuals opted into.
        institution_email = await setting_value(self.session, "email.enabled")
        from_name = await setting_value(self.session, "email.from_name")
        emailed = 0
        for n in rows:
            n.status = NotificationStatus.sent  # in-app is now visible
            pref = await self._preference(n.recipient_user_id)
            email_ok = institution_email and (pref is None or pref.email_enabled)
            muted = bool(pref and n.template in (pref.muted_events or []))
            # F6 — quiet hours delay non-urgent notifications; the row stays 'sent' in-app but
            # the email is skipped until outside the window. A separate later run picks it up.
            from datetime import datetime
            in_quiet = self.in_quiet_window(pref, datetime.utcnow())
            if email_ok and not muted and not in_quiet:
                user = (await self.session.execute(
                    select(User).where(User.id == n.recipient_user_id)
                )).scalar_one_or_none()
                if user and user.email:
                    subject, body = _render(n.template, n.payload)
                    try:
                        await send_email(to=user.email, subject=subject, body=body, from_name=from_name)
                        emailed += 1
                    except Exception:  # email is best-effort; in-app already delivered
                        logger.warning("email delivery failed for notification %s", n.id, exc_info=True)
        await self.session.commit()
        return {"delivered": len(rows), "emailed": emailed}
