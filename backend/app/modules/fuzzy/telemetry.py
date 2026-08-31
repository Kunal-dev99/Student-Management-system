"""CB-C — Redacted logging of unmatched queries.

Never persists PII. The redactor is deliberately paranoid — it prefers over-scrubbing to
under-scrubbing. Downstream, a human reviews the redacted phrasings and decides whether to
grow the vocabulary.
"""
from __future__ import annotations

import re
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assistant.telemetry_models import AssistantUnmatchedQuery

# Redaction patterns. Order matters — refs > emails > digits so we don't turn
# "student-42" into "student-<n>" and then miss "-42".
_STUDENT_REF_RE = re.compile(r"\b[A-Za-z]{2,6}[-_/]?\d{2,8}(?:[-_/][A-Za-z0-9]{2,8})?\b")
_EMAIL_RE       = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_UUID_RE        = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_LONG_NUM_RE    = re.compile(r"\b\d{4,}\b")


def redact(query: str, *, entity_names: Iterable[str] = ()) -> str:
    """Scrub the query of anything that could identify a person.

    ``entity_names`` is the list of resolved names for THIS query — we mask them explicitly so
    even a single-token first name like "Alice" is caught (a first name alone isn't picked up
    by the ref/email/UUID regexes).
    """
    if not query:
        return ""
    scrubbed = query
    # 1) Structural patterns FIRST — otherwise a name mask can eat the local part of an email
    #    ("alice.khan@..." would collapse to "<name>.<name>@..." and the email regex misses it).
    scrubbed = _UUID_RE.sub("<uuid>", scrubbed)
    scrubbed = _EMAIL_RE.sub("<email>", scrubbed)
    scrubbed = _STUDENT_REF_RE.sub("<ref>", scrubbed)
    scrubbed = _LONG_NUM_RE.sub("<n>", scrubbed)
    # 2) Explicit name masking for anything the resolver identified. Runs AFTER structural
    #    scrubbing so a name that appeared inside an email/ref is already gone.
    for name in entity_names:
        if not name:
            continue
        for part in name.split():
            if len(part) >= 3:
                scrubbed = re.sub(rf"\b{re.escape(part)}\b", "<name>", scrubbed, flags=re.IGNORECASE)
    # 3) Collapse whitespace so multiple redactions don't leave visible seams.
    return re.sub(r"\s+", " ", scrubbed).strip()


async def log_unmatched(
    session: AsyncSession,
    *,
    original_query: str,
    entity_names: list[str],
    suggested_intents: list[dict],
    session_role: str | None = None,
) -> None:
    """Persist a redacted record of an unmatched or low-confidence query.

    Rolled back silently on any error — telemetry must never break the assistant path.
    """
    try:
        row = AssistantUnmatchedQuery(
            query_redacted=redact(original_query, entity_names=entity_names)[:500],
            original_length=len(original_query or ""),
            session_role=session_role[:80] if session_role else None,
            suggested_intents=suggested_intents[:5],
        )
        session.add(row)
        await session.commit()
    except Exception:                       # noqa: BLE001 — never fail the caller for telemetry
        await session.rollback()
