"""CB-B — Pending write-intent store.

Write intents (approve payment, hold payment, submit sign-off, ...) never execute on a fuzzy
match alone. The classifier stages the parsed action here with a short TTL and returns a
``confirm_write`` envelope carrying a `pendingId`. The user must explicitly confirm; only then
does the action run.

Design constraints:
- **Short TTL (5 minutes)** — a stale confirmation cannot execute an action the user forgot about.
- **Bound to the requester** — only the user who staged it can confirm it.
- **Single-use** — the record is popped on confirm/cancel, so re-clicking the same button never
  triggers the action twice.
- **In-memory** — process-scoped; a restart cancels every pending action.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from threading import Lock

TTL_SECONDS = 300
MAX_PENDING = 5_000


@dataclass
class Pending:
    id: str
    user_id: str
    action: str                # e.g. "approve_payment"
    target: dict               # {"kind": "stipend_payment", "id": "...", "label": "..."}
    args: dict                 # what will be passed to the write handler
    diff: dict                 # human-visible before/after preview
    stored_at: float


@dataclass
class _Store:
    entries: dict[str, Pending] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)


_STORE = _Store()


def _now() -> float:
    return time.monotonic()


def _sweep(now: float) -> None:
    expired = [k for k, v in _STORE.entries.items() if now - v.stored_at > TTL_SECONDS]
    for k in expired:
        _STORE.entries.pop(k, None)
    if len(_STORE.entries) > MAX_PENDING:
        oldest = sorted(_STORE.entries.items(), key=lambda kv: kv[1].stored_at)
        for k, _ in oldest[: len(_STORE.entries) - MAX_PENDING]:
            _STORE.entries.pop(k, None)


def stage(user_id: str, *, action: str, target: dict, args: dict, diff: dict) -> Pending:
    p = Pending(
        id=str(uuid.uuid4()), user_id=user_id, action=action,
        target=target, args=args, diff=diff, stored_at=_now(),
    )
    with _STORE.lock:
        _sweep(_now())
        _STORE.entries[p.id] = p
    return p


def pop(user_id: str, pending_id: str) -> Pending | None:
    """Consume a pending record. Returns None if missing, expired, or user mismatch."""
    with _STORE.lock:
        _sweep(_now())
        p = _STORE.entries.get(pending_id)
        if p is None or p.user_id != user_id:
            return None
        _STORE.entries.pop(pending_id, None)
        return p


def peek(user_id: str, pending_id: str) -> Pending | None:
    with _STORE.lock:
        _sweep(_now())
        p = _STORE.entries.get(pending_id)
        if p is None or p.user_id != user_id:
            return None
        return p


def clear_all() -> None:
    """Test hook."""
    with _STORE.lock:
        _STORE.entries.clear()
