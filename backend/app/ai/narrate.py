"""Narrate shape — one paragraph of prose over deterministic evidence.

The prompt forbids figures not present in `evidence.figures`, and the caller renders
those figures verbatim beside the paragraph. Fallback is a deterministic template that
substitutes the same figures into a plain sentence — the reader still gets an answer.
"""
from __future__ import annotations

import logging
import string

from app.ai.client import ShapeError, call_json
from app.ai.types import Evidence, Narration, Provenance
from app.core.llm.provider import LLMError

log = logging.getLogger(__name__)


_SYSTEM = """You write a single short paragraph summarising the evidence for a reader.
Rules:
- Return JSON: {"body": "<paragraph, ≤ 60 words>"}
- Every number or date you name MUST appear in the evidence figures, spelled exactly.
- Every FACT you name — actions, milestones, funding, events — MUST come from the evidence
  context. Never invent categories the evidence didn't mention (e.g. don't mention
  "upcoming milestones" unless a milestone appears in the evidence).
- If the evidence lists no items in a category, don't refer to that category at all.
- Do not invent trends or causes. Do not editorialise about the future.
- Neutral, informational voice. No exclamation, no rhetorical questions, no metaphors.
"""


async def narrate(
    *,
    evidence: Evidence,
    question: str,
    fallback_template: str,
) -> Narration:
    """Write a paragraph. Falls back to `fallback_template.format(**figures)`.

    The template uses Python `str.format` placeholders — `{figure_name}` — and receives
    every figure in `evidence.figures`. Keep it deterministic and boring: the fallback's
    only job is to keep the feature working with the model off.
    """
    user = _format_user(question, evidence)
    try:
        # Groq's `openai/gpt-oss-*` models are chain-of-thought reasoners — they burn
        # hundreds of tokens on internal deliberation before emitting a single character
        # of the response. Under json_object mode, running out of tokens mid-stream
        # invalidates the whole reply. 3000 gives plenty of headroom for a 55-word
        # paragraph plus the reasoning phase; the actual response is still tiny.
        outcome = await call_json(system=_SYSTEM, user=user, max_tokens=3000)
    except (LLMError, ShapeError) as exc:
        log.info("narrate: falling back — %s", exc)
        return _fallback(evidence, fallback_template, reason=str(exc))

    body = outcome.payload.get("body")
    if not isinstance(body, str) or not body.strip():
        return _fallback(evidence, fallback_template, reason="empty body")

    # Grounding: every numeric-looking token in the prose must appear in the figures.
    ungrounded = _ungrounded_numbers(body, evidence.figures)
    if ungrounded:
        log.info("narrate: ungrounded figures %s — falling back", ungrounded)
        return _fallback(evidence, fallback_template, reason=f"ungrounded: {ungrounded[:2]}")

    return Narration(
        body=body.strip(),
        provenance=Provenance(source="model", model=outcome.model, latency_ms=outcome.latency_ms),
    )


def _fallback(evidence: Evidence, template: str, reason: str) -> Narration:
    try:
        body = template.format(**evidence.figures)
    except (KeyError, IndexError):
        # A missing figure in the template shouldn't crash the feature — render as-is.
        body = template
    return Narration(body=body, provenance=Provenance(source="fallback", reason=reason))


def _format_user(question: str, evidence: Evidence) -> str:
    lines = [f"Question: {question}", "", "Evidence figures (quote verbatim):"]
    for k, v in evidence.figures.items():
        lines.append(f"- {k}: {v}")
    if evidence.context:
        lines.append("")
        lines.append("Context:")
        for k, v in evidence.context.items():
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def _ungrounded_numbers(body: str, figures: dict[str, str]) -> list[str]:
    """Numeric tokens in `body` that don't appear in any figure value.

    A "numeric token" is a run of digits with optional decimal + optional % suffix. Years
    inside allowed figures are automatically covered because the figure values are text.
    """
    allowed = " ".join(figures.values())
    out: list[str] = []
    for token in _numeric_tokens(body):
        if token not in allowed:
            out.append(token)
    return out


def _numeric_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current = ""
    valid = string.digits + ".%,"
    for ch in text:
        if ch in valid:
            current += ch
        else:
            if any(c.isdigit() for c in current):
                tokens.append(current.strip(".,"))
            current = ""
    if any(c.isdigit() for c in current):
        tokens.append(current.strip(".,"))
    return tokens
