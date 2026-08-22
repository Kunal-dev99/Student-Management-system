"""Concept graph + spreading activation (Phase 5.1c) — the flexible fallback.

The strict parser in `intents.py` matches known phrasings exactly: fast and certain, but brittle.
Anything it misses used to dead-end at "I didn't understand".

This module makes that path *graceful* instead, using a classic pre-LLM technique:

1. **Tokenise + stem + fuzzy-correct** each word (so "supervsion", "supervising", "supervisor"
   all reach the same lexicon entry).
2. **Activate concepts.** Each token contributes weighted activation to one or more concept
   nodes (MEETING, FUNDING, EXPIRY, NEGATION, …).
3. **Spread activation** one hop along weighted edges, so related concepts reinforce each other
   — "hasn't been seen by anyone" lights MEETING, which spreads to SUPERVISION.
4. **Score filters** conjunctively: a filter needs every one of its concept groups to be active,
   and scores as the weakest of them.

The result is a confidence number rather than a yes/no, which lets the assistant answer a
half-recognised question *and say how sure it was*, instead of refusing. Still fully on-premise,
still deterministic, still ~1ms.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from difflib import get_close_matches

# --------------------------------------------------------------------------------------
# Concepts
# --------------------------------------------------------------------------------------

SUPERVISION = "SUPERVISION"
MEETING = "MEETING"
FUNDING = "FUNDING"
EXPIRY = "EXPIRY"
MILESTONE = "MILESTONE"
THESIS = "THESIS"
NEGATION = "NEGATION"
OVERDUE = "OVERDUE"
RISK = "RISK"
ATTRITION = "ATTRITION"
STUDENT = "STUDENT"
COUNT = "COUNT"
TIME = "TIME"

# token (already stemmed) -> {concept: weight}
_RAW_LEXICON: dict[str, dict[str, float]] = {
    # supervision / meetings
    "supervis": {SUPERVISION: 1.0},
    "supervisor": {SUPERVISION: 1.0},
    "supervisory": {SUPERVISION: 1.0},
    "meet": {MEETING: 0.9},
    "meeting": {MEETING: 1.0},
    "met": {MEETING: 0.9},
    "seen": {MEETING: 0.5},
    "see": {MEETING: 0.35},
    "contact": {MEETING: 0.6},
    "catch": {MEETING: 0.3},
    "spoken": {MEETING: 0.4},
    "check": {MEETING: 0.3},
    # funding
    "fund": {FUNDING: 1.0},
    "funding": {FUNDING: 1.0},
    "stipend": {FUNDING: 0.95},
    "scholarship": {FUNDING: 0.9},
    "bursary": {FUNDING: 0.9},
    "grant": {FUNDING: 0.7},
    "money": {FUNDING: 0.5},
    "pay": {FUNDING: 0.4},
    "unfund": {FUNDING: 1.0, NEGATION: 0.9},
    "sponsor": {FUNDING: 0.6},
    # expiry
    "expir": {EXPIRY: 1.0},
    "end": {EXPIRY: 0.7},
    "run": {EXPIRY: 0.35},
    "finish": {EXPIRY: 0.6},
    "lapse": {EXPIRY: 0.8, NEGATION: 0.4},
    "cease": {EXPIRY: 0.6},
    "up": {EXPIRY: 0.15},
    # progression
    "milestone": {MILESTONE: 1.0},
    "progression": {MILESTONE: 0.9},
    "review": {MILESTONE: 0.7},
    "panel": {MILESTONE: 0.5},
    "confirmation": {MILESTONE: 0.5},
    # thesis
    "thesis": {THESIS: 1.0},
    "dissertation": {THESIS: 0.9},
    "viva": {THESIS: 0.8},
    "examin": {THESIS: 0.6},
    # negation / absence
    "no": {NEGATION: 0.9},
    "not": {NEGATION: 0.9},
    "never": {NEGATION: 1.0},
    "without": {NEGATION: 1.0},
    "lack": {NEGATION: 0.9},
    "miss": {NEGATION: 0.8, OVERDUE: 0.5},
    "absent": {NEGATION: 0.9},
    "none": {NEGATION: 0.8},
    "nobody": {NEGATION: 0.9},
    "anyone": {NEGATION: 0.2},
    "yet": {NEGATION: 0.5},
    "haven": {NEGATION: 0.8},
    "hasn": {NEGATION: 0.8},
    # overdue / lateness
    "overdue": {OVERDUE: 1.0, NEGATION: 0.7},
    "late": {OVERDUE: 0.9, NEGATION: 0.5},
    "behind": {OVERDUE: 0.85, NEGATION: 0.5},
    "outstand": {OVERDUE: 0.7, NEGATION: 0.4},
    "stale": {OVERDUE: 0.7, NEGATION: 0.5},
    "neglect": {OVERDUE: 0.8, NEGATION: 0.6},
    "slip": {OVERDUE: 0.5, NEGATION: 0.3},
    "due": {OVERDUE: 0.4},
    # risk / attrition
    "risk": {RISK: 1.0},
    "struggl": {RISK: 0.9},
    "fail": {RISK: 0.7},
    "trouble": {RISK: 0.8},
    "concern": {RISK: 0.7},
    "worri": {RISK: 0.7},
    "crack": {RISK: 0.6},
    "flounder": {RISK: 0.7},
    "drop": {ATTRITION: 0.8},
    "quit": {ATTRITION: 0.9},
    "leav": {ATTRITION: 0.6},
    "withdraw": {ATTRITION: 0.9},
    "attrit": {ATTRITION: 1.0},
    "disengag": {RISK: 0.8},
    # subject / shape of question
    "student": {STUDENT: 1.0},
    "researcher": {STUDENT: 0.8},
    "candidat": {STUDENT: 0.6},
    "phd": {STUDENT: 0.5},
    "pgr": {STUDENT: 0.6},
    "who": {STUDENT: 0.4, COUNT: 0.2},
    "which": {STUDENT: 0.3},
    "list": {COUNT: 0.5},
    "many": {COUNT: 0.8},
    "count": {COUNT: 0.9},
    "show": {COUNT: 0.3},
    "day": {TIME: 0.8},
    "week": {TIME: 0.8},
    "month": {TIME: 0.8},
    "year": {TIME: 0.8},
}

# concept -> {neighbour: weight}. One hop of spreading activation.
EDGES: dict[str, dict[str, float]] = {
    MEETING: {SUPERVISION: 0.55},        # in this domain a "meeting" is usually supervision
    SUPERVISION: {MEETING: 0.35},
    EXPIRY: {FUNDING: 0.35},             # things that "expire" here are usually funding
    ATTRITION: {RISK: 0.8},
    OVERDUE: {NEGATION: 0.6},
    MILESTONE: {OVERDUE: 0.15},
}

DAMPING = 0.6
_SUFFIXES = ("ingly", "ing", "edly", "ed", "es", "s", "ly")


def stem(word: str) -> str:
    """Cheap suffix stripper — enough to unify expire/expiring/expired, meet/meeting/meets.

    Includes the doubled-consonant rule so "running" -> "run" (not "runn") and "stopped" ->
    "stop". `s`, `l` and `z` are excluded, as in Porter, because doubles there are usually real
    ("pass", "still").
    """
    w = word.lower()
    for suf in _SUFFIXES:
        if len(w) - len(suf) >= 3 and w.endswith(suf):
            w = w[: -len(suf)]
            if len(w) >= 3 and w[-1] == w[-2] and w[-1] not in "slz" and w[-1] not in "aeiou":
                w = w[:-1]
            return w
    return w


# Lexicon keyed by stem, so lookups and entries always agree.
LEXICON: dict[str, dict[str, float]] = {}
for _k, _v in _RAW_LEXICON.items():
    LEXICON.setdefault(stem(_k), {}).update(_v)

_LEX_KEYS = list(LEXICON)
_WORD_RE = re.compile(r"[a-z']+")


def tokenise(text: str) -> list[str]:
    return [stem(w) for w in _WORD_RE.findall((text or "").lower())]


def _lookup(token: str) -> dict[str, float] | None:
    """Exact hit, else a close match — so typos still land ('supervsion' -> 'supervis')."""
    if token in LEXICON:
        return LEXICON[token]
    if len(token) >= 4:
        near = get_close_matches(token, _LEX_KEYS, n=1, cutoff=0.82)
        if near:
            # Slightly discount a fuzzy hit; it is a guess, not a match.
            return {c: w * 0.85 for c, w in LEXICON[near[0]].items()}
    return None


def activate(text: str) -> dict[str, float]:
    """Token activation + one damped propagation hop through the concept graph."""
    act: dict[str, float] = defaultdict(float)
    for token in tokenise(text):
        hit = _lookup(token)
        if hit:
            for concept, weight in hit.items():
                act[concept] += weight

    spread: dict[str, float] = defaultdict(float)
    for concept, score in act.items():
        for neighbour, weight in EDGES.get(concept, {}).items():
            spread[neighbour] += score * weight * DAMPING
    for concept, score in spread.items():
        act[concept] += score

    # Squash into 0..1 so thresholds mean the same thing regardless of sentence length.
    return {c: min(1.0, s) for c, s in act.items()}


# --------------------------------------------------------------------------------------
# Filter scoring
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ConceptRule:
    key: str                                   # cohort_query arg, or "@intent:<tool>"
    groups: tuple[frozenset[str], ...]         # every group must fire (AND); any member counts (OR)
    kind: str                                  # "duration" | "bool" | "intent"
    label: str
    default_days: int | None = None
    veto: frozenset[str] = frozenset()         # concepts that disqualify this rule


RULES: tuple[ConceptRule, ...] = (
    ConceptRule(
        key="noSupervisionMeetingInDays",
        groups=(frozenset({SUPERVISION, MEETING}), frozenset({NEGATION, OVERDUE})),
        kind="duration", label="no supervision meeting", default_days=90,
    ),
    ConceptRule(
        key="fundingExpiringWithinDays",
        groups=(frozenset({FUNDING}), frozenset({EXPIRY})),
        kind="duration", label="funding expiring", default_days=180,
    ),
    ConceptRule(
        key="noActiveFunding",
        groups=(frozenset({FUNDING}), frozenset({NEGATION})),
        kind="bool", label="no active funding",
        veto=frozenset({EXPIRY}),              # "funding expiring" is a different question
    ),
    ConceptRule(
        key="milestoneOverdue",
        groups=(frozenset({MILESTONE}), frozenset({OVERDUE, NEGATION})),
        kind="bool", label="milestone overdue",
    ),
    ConceptRule(
        key="@intent:get_analytics",
        groups=(frozenset({RISK, ATTRITION}),),
        kind="intent", label="students flagged at risk",
    ),
)


@dataclass
class Candidate:
    rule: ConceptRule
    score: float


def score_rules(activation: dict[str, float]) -> list[Candidate]:
    """Conjunctive scoring: a rule is only as strong as its weakest required group."""
    out: list[Candidate] = []
    for rule in RULES:
        if any(activation.get(v, 0.0) >= 0.5 for v in rule.veto):
            continue
        group_scores = [max((activation.get(c, 0.0) for c in group), default=0.0) for group in rule.groups]
        if not group_scores or min(group_scores) <= 0.0:
            continue
        out.append(Candidate(rule, round(min(group_scores), 3)))
    return sorted(out, key=lambda c: c.score, reverse=True)


# A rule this strong is treated as understood; below LOW it is not offered at all.
HIGH_CONFIDENCE = 0.75
LOW_CONFIDENCE = 0.34
