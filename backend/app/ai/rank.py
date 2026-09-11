"""Rank shape — pick top N from a bounded list, one sentence of reasoning per pick.

The candidate list is produced by the caller's deterministic code (a service that reads
state and scores). The model is only allowed to pick ids that are in the list; anything
else is rejected and the fallback takes over.

Fallback: sort by `score` descending and take the first N, with a rule-based reason.
"""
from __future__ import annotations

import logging

from app.ai.client import ShapeError, call_json
from app.ai.types import Candidate, Provenance, RankPick, RankResult
from app.core.llm.provider import LLMError

log = logging.getLogger(__name__)


_SYSTEM = """You rank a bounded list of candidates and explain each pick in one sentence.
Rules:
- Return JSON: {"picks": [{"id": "<from list>", "reasoning": "<one sentence, ≤ 24 words>"}]}
- Every id MUST be one of the candidate ids you are given, verbatim.
- Never invent an id. Never invent facts. Reason only from the facts on each candidate.
- Choose exactly the requested number of picks unless fewer candidates are supplied.
- Reasoning names ONE concrete fact from the candidate — no generic praise.
"""


async def rank(
    *,
    question: str,
    candidates: list[Candidate],
    top_n: int = 5,
) -> RankResult:
    """Pick top-N candidates. Falls back to score-sorted picks if the model is unusable."""

    if not candidates:
        return RankResult(picks=[], provenance=Provenance(source="fallback",
                                                         reason="no candidates"))

    allowed = {c.id for c in candidates}
    by_id = {c.id: c for c in candidates}
    n = min(top_n, len(candidates))

    user = _format_user(question, candidates, n)
    try:
        # gpt-oss reasoners need generous max_tokens or the JSON never completes —
        # see the note in narrate.py for why.
        outcome = await call_json(system=_SYSTEM, user=user, max_tokens=3000)
    except (LLMError, ShapeError) as exc:
        log.info("rank: falling back — %s", exc)
        return _fallback(candidates, n, str(exc))

    raw_picks = outcome.payload.get("picks")
    if not isinstance(raw_picks, list):
        return _fallback(candidates, n, "picks not a list")

    seen: set[str] = set()
    picks: list[RankPick] = []
    for row in raw_picks:
        if not isinstance(row, dict):
            continue
        rid = row.get("id")
        reason = row.get("reasoning")
        if not isinstance(rid, str) or rid not in allowed or rid in seen:
            continue
        if not isinstance(reason, str) or not reason.strip():
            continue
        seen.add(rid)
        picks.append(RankPick(id=rid, reasoning=reason.strip()))
        if len(picks) >= n:
            break

    if len(picks) < n:
        # Model dropped candidates or emitted duplicates — pad from the deterministic order
        # so the caller always gets a full result of length n. Belt-and-braces.
        for c in _score_sorted(candidates):
            if c.id in seen:
                continue
            picks.append(RankPick(id=c.id, reasoning=_rule_reason(c)))
            seen.add(c.id)
            if len(picks) >= n:
                break

    return RankResult(
        picks=picks,
        provenance=Provenance(source="model", model=outcome.model, latency_ms=outcome.latency_ms),
    )


def _fallback(candidates: list[Candidate], n: int, reason: str) -> RankResult:
    picks = [
        RankPick(id=c.id, reasoning=_rule_reason(c))
        for c in _score_sorted(candidates)[:n]
    ]
    return RankResult(picks=picks, provenance=Provenance(source="fallback", reason=reason))


def _score_sorted(candidates: list[Candidate]) -> list[Candidate]:
    return sorted(candidates, key=lambda c: (c.score is None, -(c.score or 0.0)))


def _rule_reason(c: Candidate) -> str:
    facts = c.facts
    if "reasons" in facts and isinstance(facts["reasons"], list) and facts["reasons"]:
        return f"Flagged by: {', '.join(facts['reasons'][:2])}."
    if c.score is not None:
        return f"Priority score {c.score:.1f} (rule-based)."
    return "Selected by deterministic ordering."


def _format_user(question: str, candidates: list[Candidate], n: int) -> str:
    lines = [
        f"Question: {question}",
        f"Pick the top {n} from this list.",
        "",
        "Candidates:",
    ]
    for c in candidates:
        parts = [f"- id: {c.id}", f"  label: {c.label}"]
        if c.score is not None:
            parts.append(f"  score: {c.score}")
        for k, v in c.facts.items():
            parts.append(f"  {k}: {v}")
        lines.extend(parts)
    return "\n".join(lines)
