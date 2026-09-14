"""Read shape — extract fields from unstructured text into a fixed schema.

The caller supplies a Pydantic schema; the model fills its fields; anything that doesn't
match the schema is dropped and the field left blank for manual entry. Fallback is an
empty extraction with `needs_manual=True`.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.client import ShapeError, call_json
from app.ai.types import Provenance, ReadResult
from app.core.llm.provider import LLMError

log = logging.getLogger(__name__)


_SYSTEM = """You extract structured fields from a passage of text.
Rules:
- Return JSON matching the field spec exactly. Missing fields → null.
- Never invent facts absent from the text. If a field isn't stated, use null.
- Do not paraphrase dates or numbers. Copy them as written.
- Reply with the JSON object only. No commentary.
"""


async def read(
    *,
    text: str,
    schema: type[BaseModel],
    hint: str | None = None,
) -> ReadResult:
    """Extract `schema` fields from `text`. Falls back to a blank extraction."""

    field_spec = _describe_schema(schema)
    user_parts = [
        f"Field spec:\n{field_spec}",
        "",
        f"Text:\n{text}",
    ]
    if hint:
        user_parts.insert(0, f"Hint: {hint}\n")

    try:
        # Same chain-of-thought headroom issue as classify.py — 700 was marginal for
        # multi-field schemas (Case Insights' 3-field, 2-4-item-list shape) and risked
        # the same silent truncate-then-fallback failure mode under load.
        outcome = await call_json(system=_SYSTEM, user="\n".join(user_parts), max_tokens=2000)
    except (LLMError, ShapeError) as exc:
        log.info("read: falling back — %s", exc)
        return _fallback(schema, reason=str(exc))

    try:
        validated = schema.model_validate(outcome.payload)
    except ValidationError as exc:
        log.info("read: response failed schema — %s", exc)
        return _fallback(schema, reason="response failed schema")

    fields = validated.model_dump()
    warnings = _warn(fields)
    needs_manual = all(v in (None, "", []) for v in fields.values())
    return ReadResult(
        fields=fields,
        warnings=warnings,
        needs_manual=needs_manual,
        provenance=Provenance(source="model", model=outcome.model, latency_ms=outcome.latency_ms),
    )


def _fallback(schema: type[BaseModel], reason: str) -> ReadResult:
    empty = {name: None for name in schema.model_fields}
    return ReadResult(
        fields=empty,
        warnings=[],
        needs_manual=True,
        provenance=Provenance(source="fallback", reason=reason),
    )


def _describe_schema(schema: type[BaseModel]) -> str:
    lines = []
    for name, field in schema.model_fields.items():
        annotation = field.annotation
        desc = field.description or ""
        lines.append(f"- {name}: {getattr(annotation, '__name__', str(annotation))}  # {desc}")
    return "\n".join(lines)


def _warn(fields: dict[str, Any]) -> list[str]:
    """Simple, deterministic warnings — a date on a Sunday, a negative number, etc.

    Callers layer domain-specific warnings on top; we only flag universally-suspicious
    values here so the review UI has something to show even for generic schemas.
    """
    warnings: list[str] = []
    for name, value in fields.items():
        if isinstance(value, (int, float)) and value < 0:
            warnings.append(f"{name} is negative — check.")
    return warnings
