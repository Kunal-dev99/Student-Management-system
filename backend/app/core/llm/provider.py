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
import logging
import time
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings

log = logging.getLogger(__name__)


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


class OpenRouterProvider:
    """OpenRouter — OpenAI-compatible REST API, chosen here for its free-tier models.

    No SDK dependency: OpenRouter's `/chat/completions` is a plain OpenAI-shaped POST,
    and `httpx` is already a core dependency, so this needs nothing extra installed.
    """

    name = "openrouter"

    _ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self, api_key: str, model: str, timeout_seconds: float = 45.0,
        site_url: str = "", site_name: str = "",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._site_url = site_url
        self._site_name = site_name

    async def complete(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = False,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        import httpx

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        # Optional but recommended by OpenRouter — attributes traffic on their public
        # rankings page. Harmless to omit; the API works either way.
        if self._site_url:
            headers["HTTP-Referer"] = self._site_url
        if self._site_name:
            headers["X-Title"] = self._site_name

        body: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._ENDPOINT, headers=headers, json=body)
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPStatusError as exc:
            # OpenRouter puts the useful detail in the JSON body, not the status line —
            # a bare "429" or "404" tells the caller nothing about WHY (rate limit vs
            # a retired free model vs a bad key).
            detail = exc.response.text[:300]
            raise LLMError(f"OpenRouter request failed ({exc.response.status_code}): {detail}") from exc
        except Exception as exc:
            raise LLMError(f"OpenRouter request failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            choice = payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise LLMError(f"OpenRouter returned an unexpected response shape: {payload}") from exc
        usage = payload.get("usage") or {}
        return LLMResponse(
            text=choice,
            model=payload.get("model", self._model),
            tokens_in=usage.get("prompt_tokens", 0) or 0,
            tokens_out=usage.get("completion_tokens", 0) or 0,
            latency_ms=latency_ms,
        )


class FallbackProvider:
    """Tries each underlying provider in order; only raises once every one has failed.

    This is what makes "no static fallback while a live model exists" true: a shape
    module (classify/narrate/read/rank) only ever drops to its keyword-rule/template
    fallback when `LLMError` reaches it — with this wrapper as the resolved provider,
    that only happens after Groq AND OpenRouter have both actually failed, not after
    the first one hiccups. `name`/the returned `LLMResponse.model` reflect whichever
    provider actually answered, so telemetry and the UI's "AI narration" badge show
    the real engine, not a generic "fallback_chain" label.
    """

    def __init__(self, providers: list[LLMProvider]) -> None:
        if not providers:
            raise ValueError("FallbackProvider needs at least one underlying provider")
        self._providers = providers

    @property
    def name(self) -> str:
        # Read by `provider_is_live()` — true as long as at least one real provider
        # is in the chain (MockProvider is never placed in a chain, see get_provider).
        return self._providers[0].name

    async def complete(
        self,
        *,
        system: str,
        user: str,
        json_mode: bool = False,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        errors: list[str] = []
        for i, provider in enumerate(self._providers):
            try:
                response = await provider.complete(
                    system=system, user=user, json_mode=json_mode,
                    max_tokens=max_tokens, temperature=temperature,
                )
                if i > 0:
                    log.warning(
                        "LLM fallback engaged: %s failed (%s), %s answered instead",
                        self._providers[0].name, errors[0] if errors else "?", provider.name,
                    )
                return response
            except LLMError as exc:
                errors.append(str(exc))
                log.info("provider %s failed, trying next: %s", provider.name, exc)
                continue
        raise LLMError(
            "All configured LLM providers failed: "
            + "; ".join(f"{p.name}: {e}" for p, e in zip(self._providers, errors))
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
    """Resolve the live provider chain, falling back to the mock only when NO key exists.

    Every configured live provider is tried, Groq first then OpenRouter, before a
    caller ever sees `LLMError` — that's what keeps a shape module (classify/narrate/
    read/rank) from dropping to its keyword-rule/template fallback just because one
    provider had a bad moment. `llm_provider="mock"` is the explicit escape hatch
    (tests, or deliberately running with no live model); any other value builds the
    best chain available from whichever keys ARE configured, regardless of which one
    the setting names — a deployment with only an OpenRouter key still works even
    though the default setting value is "groq".

    `planner=True` returns each provider's smaller, faster model for the planning
    phase. An empty chain (no keys anywhere) still returns the mock — a missing key
    should degrade the composer, not break the deployment.
    """
    settings = get_settings()
    if settings.llm_provider == "mock":
        return MockProvider()

    chain: list[LLMProvider] = []
    if settings.groq_api_key:
        chain.append(GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.llm_planner_model if planner else settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        ))
    if settings.openrouter_api_key:
        chain.append(OpenRouterProvider(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_planner_model if planner else settings.openrouter_model,
            timeout_seconds=settings.llm_timeout_seconds,
            site_url=settings.openrouter_site_url,
            site_name=settings.openrouter_site_name,
        ))
    if not chain:
        return MockProvider()
    return chain[0] if len(chain) == 1 else FallbackProvider(chain)


def provider_is_live() -> bool:
    """True when a real model is reachable — drives the "LLM unavailable" UI state."""
    return get_provider().name != "mock"
