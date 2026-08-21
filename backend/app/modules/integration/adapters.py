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


async def deliver(adapter: Adapter, event_type: str, payload: dict) -> dict:
    """Translate, then deliver.

    If a partner URL is configured for this adapter's system (INTEGRATION_<SYSTEM>_URL), POST the
    translated message over HTTP and raise on a non-2xx / network error so the outbox can retry and
    eventually dead-letter it. With no URL configured, delivery is a translate-only stand-in that
    always succeeds (the Phase 1–3 behaviour).
    """
    from app.core.config import get_settings

    message = adapter.translate(event_type, payload)
    settings = get_settings()
    url = getattr(settings, f"integration_{adapter.system}_url", None)
    if not url:
        return message

    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=message)
        resp.raise_for_status()
    return {**message, "deliveredTo": url, "httpStatus": resp.status_code}
