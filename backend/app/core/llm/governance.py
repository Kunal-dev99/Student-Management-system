"""What has to be true before a prompt is allowed to leave the building.

Four gates, checked in order — cheapest first:

1. **Kill switch.** `composer.enabled` is an institution setting, default off. An admin
   turns the composer on for their institution; nobody else can.
2. **Provider.** No API key means no live model. Callers get a clear reason, not a 500.
3. **Budget.** A per-user daily token ceiling, so a runaway client cannot burn the account.
4. **Redaction.** Audit rows never store raw prompts — student names, emails, refs and
   identifiers are masked before anything is written down.

Redaction applies to what we *record*, not to what we *send*. The composer has to see real
names to put them in a table. Tenants that cannot allow that get pseudonymisation instead,
which is a data-function concern (labels replaced at source, restored on render) and is
tracked separately — this module deliberately does not pretend to solve it.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.provider import provider_is_live


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reason: str | None = None


# Structural patterns run before name masking — an email's local part would otherwise be
# eaten by the name pass, leaving a half-redacted address in the log.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "«id»"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "«email»"),
    (re.compile(r"\b[A-Z]{2,6}-\d{4}-[A-Z0-9]{4,8}\b"), "«ref»"),
    (re.compile(r"\b\d{9,}\b"), "«num»"),
)


def redact(text: str, *, names: list[str] | None = None) -> str:
    """Mask identifiers for storage. Order matters — see the module docstring."""
    out = text
    for pattern, replacement in _PATTERNS:
        out = pattern.sub(replacement, out)
    for name in sorted(names or [], key=len, reverse=True):
        if len(name) < 3:
            continue
        out = re.sub(rf"\b{re.escape(name)}\b", "«name»", out, flags=re.I)
    return out


async def check_enabled(session: AsyncSession) -> GateResult:
    """Gates 1 and 2 — institution opt-in, then a reachable model."""
    from app.modules.settings.service import setting_value

    try:
        enabled = await setting_value(session, "composer.enabled")
    except KeyError:
        # Setting not registered yet (pre-migration deployment) — fail closed.
        return GateResult(False, "The composer is not configured for this institution.")

    if not enabled:
        return GateResult(
            False,
            "The composer is switched off for this institution. "
            "An administrator can enable it under Settings → Institution policy.",
        )
    if not provider_is_live():
        return GateResult(
            False,
            "No language model is configured on this deployment, so compositions "
            "cannot be generated.",
        )
    return GateResult(True)


async def check_budget(
    session: AsyncSession, *, user_id: uuid.UUID, requested: int
) -> GateResult:
    """Gate 3 — today's tokens for this user against the institution's daily ceiling.

    Charged against completions already recorded, so an in-flight request cannot be
    double-counted and a crashed one cannot leak budget.
    """
    from app.modules.composer.models import ComposerRun
    from app.modules.settings.service import setting_value

    try:
        ceiling = int(await setting_value(session, "composer.daily_token_budget"))
    except (KeyError, TypeError, ValueError):
        return GateResult(True)

    if ceiling <= 0:
        return GateResult(True)

    used = (
        await session.execute(
            select(func.coalesce(func.sum(ComposerRun.tokens_in + ComposerRun.tokens_out), 0))
            .where(ComposerRun.user_id == user_id)
            .where(func.date(ComposerRun.created_at) == date.today())
        )
    ).scalar_one()

    if int(used) + requested > ceiling:
        return GateResult(
            False,
            f"Daily composer budget reached ({int(used):,} of {ceiling:,} tokens). "
            "It resets at midnight, or an administrator can raise the limit.",
        )
    return GateResult(True)
