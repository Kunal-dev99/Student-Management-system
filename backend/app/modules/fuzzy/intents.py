"""Intent registry — loads every vocab/*.py and exposes them as Intent objects.

Each vocab file is a plain Python module (reviewable in PR, no DB). This module discovers
them at import time.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Intent:
    name: str                          # unique intent id
    group: str                         # human-facing lens ("finance", "people", ...)
    description: str
    core_tokens: frozenset[str]        # strong evidence
    adjacent_tokens: frozenset[str]    # supporting evidence
    negative_tokens: frozenset[str]    # presence PENALISES this intent
    examples: tuple[str, ...]
    optional_slots: frozenset[str]     # {"person", "window", ...}
    tool: str                          # bound tool name
    card: str                          # card spec id for the FE renderer
    default_args: dict[str, Any] = field(default_factory=dict)
    # How strongly a resolved entity boosts this intent. Set >1 for intents where the presence
    # of a named person is the primary signal (student_summary). Filter/cohort intents that
    # merely ACCEPT a person slot should stay at 1.0 so a bare "Alice" doesn't tie them with
    # student_summary.
    entity_weight: float = 1.0
    # CB-B — when set, this intent MUTATES. It never runs directly; instead the router stages a
    # pending record and returns a confirm_write envelope. The value is the write-action id the
    # execute step looks up.
    write_action: str | None = None
    # Permission code the write action requires ON TOP OF assistant.use.
    write_permission: str | None = None


class IntentRegistry:
    def __init__(self, intents: list[Intent]) -> None:
        self._by_name = {i.name: i for i in intents}

    def all(self) -> list[Intent]:
        return list(self._by_name.values())

    def by_name(self, name: str) -> Intent | None:
        return self._by_name.get(name)

    def by_group(self) -> dict[str, list[Intent]]:
        out: dict[str, list[Intent]] = {}
        for i in self._by_name.values():
            out.setdefault(i.group, []).append(i)
        return out


def _load() -> IntentRegistry:
    from app.modules.fuzzy import vocab as vocab_pkg
    intents: list[Intent] = []
    for mod_info in pkgutil.iter_modules(vocab_pkg.__path__):
        mod = importlib.import_module(f"{vocab_pkg.__name__}.{mod_info.name}")
        if not hasattr(mod, "INTENT"):
            continue
        intents.append(mod.INTENT)
    return IntentRegistry(intents)


_registry: IntentRegistry | None = None


def registry() -> IntentRegistry:
    global _registry
    if _registry is None:
        _registry = _load()
    return _registry


def reload_registry() -> IntentRegistry:
    """Test hook — forces a fresh import so a new vocab file is picked up."""
    global _registry
    _registry = _load()
    return _registry
