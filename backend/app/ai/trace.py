"""Reasoning-trace emitter for SSE endpoints.

A trace is a short list of steps in the vocabulary of the user's own work. Every step
must correspond to real work happening on the server — no faked steps, and the reveal
holds at the last step until the actual response arrives.

The emitter is a thin wrapper around an `asyncio.Queue`. The route iterates it as an SSE
stream; the service pushes steps onto it as it runs.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceEmitter:
    """One-per-request trace. Push steps; the endpoint yields them as SSE."""

    _queue: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    _done: bool = False

    async def step(self, label: str, detail: str | None = None, icon: str | None = None) -> None:
        """Advance the trace. `label` is short and user-facing; `detail` is optional.

        `icon` is a soft hint the UI may map to a small graphic — the vocabulary is
        loose (`database`, `sparkles`, `pen`, `calculator`, `layout`), and unknown values
        fall back to the default dot in the UI.
        """
        await self._queue.put({"type": "step", "label": label, "detail": detail, "icon": icon})

    async def partial(self, payload: dict[str, Any]) -> None:
        """Emit an intermediate result so the UI can render it before the final one.

        Used when the deterministic part of a feature completes ahead of the AI part —
        the reader gets the evidence table immediately while the model call is still in
        flight, rather than staring at a spinner for the whole round-trip.
        """
        await self._queue.put({"type": "partial", "payload": payload})

    async def result(self, payload: dict[str, Any]) -> None:
        """Emit the final payload and close the stream."""
        await self._queue.put({"type": "result", "payload": payload})
        await self._queue.put({"type": "__done__"})

    async def error(self, message: str) -> None:
        """Emit a graceful error message rather than a raw exception."""
        await self._queue.put({"type": "error", "message": message})
        await self._queue.put({"type": "__done__"})

    async def stream(self) -> AsyncIterator[str]:
        """Yield SSE-formatted lines. Consumers hang on the queue until the trace closes."""
        while True:
            event = await self._queue.get()
            if event.get("type") == "__done__":
                return
            yield f"data: {json.dumps(event)}\n\n"
