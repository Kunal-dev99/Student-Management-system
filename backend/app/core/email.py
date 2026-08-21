"""Email delivery (arch §10.4 notifications).

Two backends, chosen by `settings.email_backend`:
- "console" (dev): logs the rendered message; never touches the network.
- "smtp"  (prod): sends via aiosmtplib using the configured relay.

Callers use `send_email(...)`; failures raise so the worker can mark the notification failed
and retry on the next tick.
"""
from __future__ import annotations

import logging
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger("pgr.email")


async def send_email(*, to: str, subject: str, body: str) -> None:
    settings = get_settings()
    if settings.email_backend == "console":
        logger.info("EMAIL (console backend)\n  To: %s\n  Subject: %s\n  %s", to, subject, body)
        return

    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    import aiosmtplib  # local import so the dev/console path needs no SMTP lib at import time

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        start_tls=settings.smtp_use_tls,
    )
    logger.info("email sent to %s (subject=%s)", to, subject)
