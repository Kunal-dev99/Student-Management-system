"""Provider-agnostic LLM access.

Everything that wants a model goes through `LLMProvider`. Groq is the current backing
service; swapping to Anthropic, OpenAI or a local Ollama is a new class plus one line in
`get_provider` — no caller changes. `MockProvider` keeps the test suite free of network
calls and API keys.

Deliberately narrow: one method, text in and text out, with token counts. No streaming, no
tool-calling round-trips, no conversation state. The composer needs a single structured
completion; anything richer belongs in a layer above this, not inside it.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings


class LLMError(RuntimeError):
    """Provider failed. Callers degrade gracefully rather than surfacing a 500."""


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int


class LLMProvider(Protocol):
    name: str

    async def complete(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = False,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse: ...


class GroqProvider:
    """Groq — chosen for latency. Composition is an interactive act: a user asks a question
    and waits for a dashboard, so time-to-first-render matters more than marginal quality."""

    name = "groq"

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 45.0) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    async def complete(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = False,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        # Imported lazily so the package stays optional — the platform boots and every
        # non-composer feature works without `groq` installed.
        try:
            from groq import AsyncGroq
        except ImportError as exc:  # pragma: no cover - depends on install profile
            raise LLMError(
                "The `groq` package is not installed. Run: pip install groq"
            ) from exc

        client = AsyncGroq(api_key=self._api_key, timeout=self._timeout)
        started = time.perf_counter()
        try:
            completion = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"} if json_mode else None,
            )
        except Exception as exc:
            raise LLMError(f"Groq request failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = completion.usage
        return LLMResponse(
            text=completion.choices[0].message.content or "",
            model=self._model,
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=latency_ms,
        )


class MockProvider:
    """Returns canned responses. Used by tests and by any environment with no API key, so
    the composer endpoints stay exercisable without a live model."""

    name = "mock"

    def __init__(self, canned: str | dict | None = None) -> None:
        if isinstance(canned, dict):
            canned = json.dumps(canned)
        self._canned = canned or json.dumps(
            {
                "title": "Mock composition",
                "blocks": [
                    {
                        "type": "narrative",
                        "body": "No language model is configured, so this is a stand-in.",
                    }
                ],
            }
        )

    async def complete(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = False,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        return LLMResponse(
            text=self._canned, model="mock", tokens_in=0, tokens_out=0, latency_ms=0
        )


def get_provider(*, planner: bool = False) -> LLMProvider:
    """Resolve the configured provider, falling back to the mock when unconfigured.

    `planner=True` returns the smaller, faster model for the planning phase. Falling back
    rather than raising is deliberate: a missing key should degrade the composer, not break
    the deployment.
    """
    settings = get_settings()
    if settings.llm_provider == "groq" and settings.groq_api_key:
        return GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.llm_planner_model if planner else settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    return MockProvider()


def provider_is_live() -> bool:
    """True when a real model is reachable — drives the "LLM unavailable" UI state."""
    return get_provider().name != "mock"
