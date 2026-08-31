"""End-to-end router: raw query -> normalise -> entities -> time -> classify -> decide."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal
from app.modules.fuzzy.classifier import IntentMatch, classify, decide
from app.modules.fuzzy.entities import ResolvedEntity, resolve_entities
from app.modules.fuzzy.normaliser import normalise
from app.modules.fuzzy.time_parser import TimeSlot, parse_time


@dataclass
class RouteDecision:
    kind: str                              # "answer" | "clarify" | "not_understood"
    query: str
    normalised_text: str
    tokens: tuple[str, ...]
    entities: list[ResolvedEntity]
    time_slot: TimeSlot | None
    matches: list[IntentMatch]
    slots: dict[str, Any] = field(default_factory=dict)

    def trace(self) -> dict:
        """Debuggable shape for the UI trace disclosure."""
        return {
            "normalised": self.normalised_text,
            "tokens": list(self.tokens),
            "entities": [
                {"kind": e.kind, "id": e.id, "name": e.name,
                 "studentRef": e.student_ref, "score": round(e.score, 3)}
                for e in self.entities
            ],
            "timeSlot": self.time_slot.as_iso() if self.time_slot else None,
            "intents": [
                {"name": m.intent.name, "score": round(m.score, 3),
                 "core": list(m.matched_core), "adjacent": list(m.matched_adjacent),
                 "negative": list(m.matched_negative), "entityAnchor": m.entity_anchor}
                for m in self.matches
            ],
        }


async def route(
    query: str, principal: Principal, session: AsyncSession,
    *, today: date | None = None,
) -> RouteDecision:
    norm = normalise(query)
    entities = await resolve_entities(query, principal, session)
    time_slot = parse_time(norm.text, today=today or date.today())

    matches = classify(norm.tokens, entities)
    kind, top = decide(matches)

    slots: dict[str, Any] = {}
    if entities:
        slots["person"] = {
            "id": entities[0].id, "name": entities[0].name,
            "studentRef": entities[0].student_ref,
        }
    if time_slot:
        slots["window"] = time_slot.as_iso()

    return RouteDecision(
        kind=kind, query=query,
        normalised_text=norm.text, tokens=norm.tokens,
        entities=entities, time_slot=time_slot,
        matches=top if kind != "answer" else matches[:1],
        slots=slots,
    )
