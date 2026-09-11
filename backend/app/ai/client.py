"""Single narrow model call, shape-checked on receipt.

Nothing here knows about ranking, reading or classifying — it just runs the prompt, parses
JSON, and either returns the payload or raises. The four shape modules (`rank`, `read`,
`classify`, `narrate`) wrap this and each supplies its own deterministic fallback.

Deliberately no retries beyond one — a slow model call should degrade to a plain paragraph
rather than a 30-second spinner.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.core.llm.provider import LLMError, LLMResponse, get_provider

log = logging.getLogger(__name__)


class ShapeError(RuntimeError):
    """Response parsed but didn't match the caller's expected shape."""


@dataclass(frozen=True)
class CallOutcome:
    """One model call's result — parsed payload plus provenance for the UI."""

    payload: dict[str, Any]
    model: str
    latency_ms: int


async def call_json(
    *,
    system: str,
    user: str,
    max_tokens: int = 800,
    temperature: float = 0.2,
) -> CallOutcome:
    """Run one JSON-mode completion and return the parsed dict.

    Raises `LLMError` if the provider is a mock (turned off) or the request fails.
    Raises `ShapeError` if the response isn't valid JSON.
    """
    provider = get_provider()
    if provider.name == "mock":
        # Rather than returning canned data, refuse — every shape module handles this by
        # running its deterministic fallback. Keeps the layer honest: the mock provider
        # doesn't accidentally look like a live model.
        raise LLMError("No live model configured")

    response: LLMResponse = await provider.complete(
        system=system,
        user=user,
        json_mode=True,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    try:
        payload = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise ShapeError(f"Model returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ShapeError("Model response was not a JSON object")
    return CallOutcome(payload=payload, model=response.model, latency_ms=response.latency_ms)
