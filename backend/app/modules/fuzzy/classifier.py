"""Scores a normalised token stream against every intent in the registry.

Scoring model (deterministic, no ML):

    score = (core_hits × 3 + adjacent_hits × 1 + verb_bonus + entity_bonus) / normaliser
          − negative_hits × 2

An intent needs at least one core-token hit OR an anchoring entity to score above zero.
Returned `IntentMatch.score` is normalised to 0..1 for easy thresholding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.modules.fuzzy.entities import ResolvedEntity
from app.modules.fuzzy.intents import Intent, registry
from app.modules.fuzzy.verbs import WRITE_VERBS, is_request_verb, is_write_verb


CONFIDENT_THRESHOLD = 0.55
CLARIFY_MARGIN = 0.15         # top-1 must beat top-2 by this to be confident


@dataclass(frozen=True)
class IntentMatch:
    intent: Intent
    score: float
    matched_core: tuple[str, ...]
    matched_adjacent: tuple[str, ...]
    matched_negative: tuple[str, ...]
    entity_anchor: bool


def _score_one(intent: Intent, tokens: Iterable[str], entities: list[ResolvedEntity]) -> IntentMatch:
    token_set = set(tokens)
    core = token_set & intent.core_tokens
    adj = token_set & intent.adjacent_tokens
    neg = token_set & intent.negative_tokens

    verb_bonus = 1.0 if any(is_request_verb(t) for t in token_set) else 0.0

    # A write verb ("approve", "hold", "sign", ...) in the query is a strong signal that the
    # user wants ACTION, not a report. Bias write-capable intents up so they beat their
    # descriptive twins ("held payments" report vs "hold this payment" action).
    has_write_verb = bool(token_set & WRITE_VERBS)
    write_bonus = 2.0 if (has_write_verb and intent.write_action) else 0.0
    write_penalty = 1.0 if (has_write_verb and not intent.write_action and (core & WRITE_VERBS)) else 0.0

    # Entity anchor — an intent that accepts a person slot gets a substantial boost when a
    # person was resolved. This is the "Alice's payments" trick: even if only a couple of
    # keywords match, presence of the person makes the intent obvious.
    entity_anchor = "person" in intent.optional_slots and bool(entities)
    # An entity boosts intents that accept a person slot; the boost is much bigger for intents
    # whose primary purpose is to talk about the named person (student_summary). Filter intents
    # that merely accept a person get only a small nudge, so a bare "alice" routes to summary.
    entity_bonus = (3.0 * intent.entity_weight) if entity_anchor else 0.0

    raw = (len(core) * 3 + len(adj) * 1 + verb_bonus + entity_bonus + write_bonus) \
          - (len(neg) * 2) - write_penalty
    # Normaliser: worst case one core token + verb.
    denom = max(3 + verb_bonus, 4.0)
    score = max(0.0, raw / denom)

    # An intent with zero core hits AND no entity anchor cannot fire — this stops adjacent-only
    # collisions ("payment" alone triggering every finance intent).
    if not core and not entity_anchor:
        score = 0.0

    # Do NOT clip to 1.0 during scoring — clipping causes ties between "clearly strong" and
    # "just barely confident". Downstream `decide()` uses the un-clipped score for ordering,
    # and the returned trace clips for display only.
    return IntentMatch(
        intent=intent, score=score,
        matched_core=tuple(sorted(core)),
        matched_adjacent=tuple(sorted(adj)),
        matched_negative=tuple(sorted(neg)),
        entity_anchor=entity_anchor,
    )


def classify(
    tokens: Iterable[str], entities: list[ResolvedEntity] | None = None,
) -> list[IntentMatch]:
    """Score every registered intent. Returns non-zero matches sorted best-first."""
    entities = entities or []
    tokens = list(tokens)
    scored = [_score_one(i, tokens, entities) for i in registry().all()]
    scored = [m for m in scored if m.score > 0]
    scored.sort(key=lambda m: -m.score)
    return scored


def decide(matches: list[IntentMatch]) -> tuple[str, list[IntentMatch]]:
    """Turn a sorted match list into a routing decision.

    Returns ("answer" | "clarify" | "not_understood", top_matches).
    """
    if not matches:
        return "not_understood", []
    top = matches[0]
    if top.score < CONFIDENT_THRESHOLD:
        return "not_understood", matches[:3]
    if len(matches) > 1 and (top.score - matches[1].score) < CLARIFY_MARGIN:
        return "clarify", matches[:3]
    return "answer", [top]
