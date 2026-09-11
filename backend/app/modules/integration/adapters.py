"""Anti-corruption adapters (arch §10.2, §10.3).

Each adapter translates a platform domain event into the shape an external system expects. The
external systems stay authoritative; the platform never becomes them. In this MVP the adapters
translate + return the outbound message (recorded in integration_log) rather than making a real
network call — real HTTP/mTLS delivery is wired when the partner endpoints exist.
"""
from __future__ import annotations

from typing import Protocol


class Adapter(Protocol):
    system: str
    def translate(self, event_type: str, payload: dict) -> dict: ...


class FinanceAdapter:
    """Sends funding-relationship events to Finance; Finance owns payment (arch §10.1)."""
    system = "finance"

    def translate(self, event_type: str, payload: dict) -> dict:
        return {
            "targetSystem": "finance",
            "message": "funding_relationship_event",
            "eventType": event_type,
            "reference": payload,
        }


class HRAdapter:
    """Notifies HR of workforce-relevant lifecycle events (e.g. graduation)."""
    system = "hr"

    def translate(self, event_type: str, payload: dict) -> dict:
        return {"targetSystem": "hr", "message": "workforce_event", "eventType": event_type, "reference": payload}


class ResearchAdapter:
    system = "research"

    def translate(self, event_type: str, payload: dict) -> dict:
        return {"targetSystem": "research", "message": "research_context_event", "eventType": event_type, "reference": payload}


# event_type -> adapters that should receive it. Events with no route are internal only.
ROUTES: dict[str, list[Adapter]] = {
    "funding.changed": [FinanceAdapter()],
    "student.graduated": [HRAdapter(), FinanceAdapter()],
}


# ---------------------------------------------------------------------------
# Adapter registry — the source of truth for what the Integration Hub knows.
# Adding an adapter here (or its metadata) is the only place a new external
# system needs registering; the UI/CRUD/routing all read from this list.
# ---------------------------------------------------------------------------

ADAPTERS: dict[str, Adapter] = {
    a.system: a for a in [FinanceAdapter(), HRAdapter(), ResearchAdapter()]
}

ADAPTER_META: dict[str, dict[str, str]] = {
    "finance":  {"label": "Finance",        "description": "Stipend payments, invoice raising, funding-relationship events (Unit4 / Agresso / SAP)."},
    "hr":       {"label": "HR",             "description": "Workforce-relevant lifecycle events (e.g. graduation) — iTrent / SAP HCM."},
    "research": {"label": "Research office", "description": "Research context events (award changes, project links) — PURE / Worktribe."},
}


async def resolve_target(session, system: str) -> tuple[str | None, bool, str]:
    """Return (url, active, source) for an adapter target.

    Resolution order: institution_setting override → environment variable → None.
    `source` is one of "db", "env", "none" so the UI can show where the value comes from.
    """
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.modules.settings.models import InstitutionSetting

    url_key = f"integration.{system}.url"
    active_key = f"integration.{system}.active"

    rows = (await session.execute(
        select(InstitutionSetting).where(InstitutionSetting.key.in_([url_key, active_key]))
    )).scalars().all()
    by_key = {r.key: r.value for r in rows}

    if url_key in by_key:
        url = (by_key[url_key] or {}).get("value") or None
        active = bool((by_key.get(active_key) or {"value": True}).get("value", True))
        return (url, active, "db" if url else "none")

    env_url = getattr(get_settings(), f"integration_{system}_url", None)
    if env_url:
        return (env_url, True, "env")
    return (None, False, "none")


async def deliver(adapter: Adapter, event_type: str, payload: dict, session=None) -> dict:
    """Translate, then deliver.

    If a partner URL is configured for this adapter's system (via the Integration Hub UI or the
    matching env var), POST the translated message over HTTP and raise on a non-2xx / network error
    so the outbox can retry and eventually dead-letter it. With no URL configured, delivery is a
    translate-only stand-in that always succeeds — the message is still recorded so nothing is lost.
    """
    from app.core.config import get_settings

    message = adapter.translate(event_type, payload)

    # Prefer DB-configured target (set from the Integration Hub UI); fall back to env.
    url: str | None = None
    active = True
    if session is not None:
        url, active, _ = await resolve_target(session, adapter.system)
    if url is None:
        url = getattr(get_settings(), f"integration_{adapter.system}_url", None)

    if not url or not active:
        return message

    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=message)
        resp.raise_for_status()
    return {**message, "deliveredTo": url, "httpStatus": resp.status_code}
