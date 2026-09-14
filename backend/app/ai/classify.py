"""Classify shape — assign one label from a fixed set, with a one-sentence reason.

The label list is closed; a label outside it is rejected and the fallback runs a
keyword-rule classifier. The caller supplies both the labels and the keyword rules for
the fallback so this module stays domain-blind.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from app.ai.client import ShapeError, call_json
from app.ai.types import ClassifyResult, Provenance
from app.core.llm.provider import LLMError

log = logging.getLogger(__name__)


_SYSTEM = """You classify an input into ONE label from a fixed list and explain the pick.
Rules:
- Return JSON: {"label": "<one of the allowed labels>", "reasoning": "<one sentence, ≤ 24 words>"}
- The label MUST be one of the allowed labels, spelled exactly.
- Never invent a new label. If nothing fits well, pick the closest.
- Reason from concrete features of the input, not general priors.
"""


KeywordRules = dict[str, list[str]]  # label → list of substrings that pick that label


async def classify(
    *,
    text: str,
    labels: list[str],
    keyword_rules: KeywordRules | None = None,
    fallback_label: str | None = None,
    context: str | None = None,
) -> ClassifyResult:
    """Assign one label. Falls back to keyword rules, then `fallback_label`."""

    if not labels:
        raise ValueError("classify requires at least one label")

    user_parts = [f"Allowed labels: {', '.join(labels)}"]
    if context:
        user_parts.append(f"Context: {context}")
    user_parts.append(f"Input:\n{text}")

    try:
        # Groq's `openai/gpt-oss-*` models are chain-of-thought reasoners — they burn
        # hundreds of tokens on internal deliberation before emitting the (tiny)
        # {label, reasoning} JSON. 200 was cutting the response off mid-reasoning,
        # producing a ShapeError and a silent drop to the keyword-rule fallback on
        # every call — narrate.py and rank.py already carry this exact fix; classify
        # was the one shape module that had been missed.
        outcome = await call_json(system=_SYSTEM, user="\n\n".join(user_parts), max_tokens=3000)
    except (LLMError, ShapeError) as exc:
        log.info("classify: falling back — %s", exc)
        return _fallback(text, labels, keyword_rules, fallback_label, reason=str(exc))

    label = outcome.payload.get("label")
    reasoning = outcome.payload.get("reasoning")
    if not isinstance(label, str) or label not in labels:
        return _fallback(text, labels, keyword_rules, fallback_label, reason="label out of set")
    if not isinstance(reasoning, str) or not reasoning.strip():
        reasoning = "Model-selected label."

    return ClassifyResult(
        label=label,
        reasoning=reasoning.strip(),
        provenance=Provenance(source="model", model=outcome.model, latency_ms=outcome.latency_ms),
    )


def _fallback(
    text: str,
    labels: list[str],
    rules: KeywordRules | None,
    fallback_label: str | None,
    reason: str,
) -> ClassifyResult:
    lowered = text.lower()
    if rules:
        for label, keywords in rules.items():
            if label not in labels:
                continue
            for kw in keywords:
                if kw.lower() in lowered:
                    return ClassifyResult(
                        label=label,
                        reasoning=f"Matched keyword rule: '{kw}'.",
                        provenance=Provenance(source="fallback", reason=reason),
                    )
    chosen = fallback_label if fallback_label in labels else labels[0]
    return ClassifyResult(
        label=chosen,
        reasoning="Default label — no keyword rule matched.",
        provenance=Provenance(source="fallback", reason=reason),
    )
