"""CB-B — Session-scoped slot memory with a hard TTL.

Purpose: multi-turn continuity. When the user says *"what about her payments?"* right after
resolving *"Alice Khan"*, the pronoun binds back to Alice. That is what turns a search box into
a chatbot.

Design constraints:
- **Session-scoped and short-lived.** A 60-second TTL means an accidentally-shared session
  cannot leak the last-viewed entity into a later, unrelated question.
- **Per user.** Keyed by user id (and optionally session id header) so two concurrent users
  never see each other's slots.
- **Bounded.** Simple dict with a hard cap on entries — evict oldest when full. Prevents an
  attacker from running the process out of memory by looping through refs.
- **In-memory.** No DB row per turn; if the process restarts, everyone starts fresh — which is
  exactly what you want for short-term conversational state.

Not a substitute for real dialogue state. This handles the one case that keeps giving:
a pronoun in a follow-up.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock

TTL_SECONDS = 60
MAX_ENTRIES = 10_000


PRONOUNS_PERSON = frozenset({"her", "him", "his", "hers", "their", "theirs", "them"})


@dataclass
class Slot:
    entity_id: str
    entity_name: str
    student_ref: str | None
    stored_at: float


@dataclass
class _Store:
    entries: dict[str, Slot] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)


_STORE = _Store()


def _now() -> float:
    return time.monotonic()


def _key(user_id: str, session_id: str | None) -> str:
    return f"{user_id}|{session_id or ''}"


def _sweep(now: float) -> None:
    """Drop expired entries; also cap the total size."""
    expired = [k for k, v in _STORE.entries.items() if now - v.stored_at > TTL_SECONDS]
    for k in expired:
        _STORE.entries.pop(k, None)
    if len(_STORE.entries) > MAX_ENTRIES:
        # Oldest-first eviction.
        oldest = sorted(_STORE.entries.items(), key=lambda kv: kv[1].stored_at)
        for k, _ in oldest[: len(_STORE.entries) - MAX_ENTRIES]:
            _STORE.entries.pop(k, None)


def remember_person(user_id: str, session_id: str | None, *, entity_id: str,
                    entity_name: str, student_ref: str | None) -> None:
    with _STORE.lock:
        _sweep(_now())
        _STORE.entries[_key(user_id, session_id)] = Slot(
            entity_id=entity_id, entity_name=entity_name,
            student_ref=student_ref, stored_at=_now(),
        )


def recall_person(user_id: str, session_id: str | None) -> Slot | None:
    with _STORE.lock:
        _sweep(_now())
        return _STORE.entries.get(_key(user_id, session_id))


def clear(user_id: str, session_id: str | None) -> None:
    with _STORE.lock:
        _STORE.entries.pop(_key(user_id, session_id), None)


def clear_all() -> None:
    """Test hook."""
    with _STORE.lock:
        _STORE.entries.clear()


def query_has_person_pronoun(tokens) -> bool:
    """True when a token stream looks like it needs pronoun resolution."""
    return any(t in PRONOUNS_PERSON for t in tokens)
