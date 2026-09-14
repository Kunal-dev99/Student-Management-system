"""Structured commitment extraction from meeting notes.

Phase 2 ships the deterministic extractor: bulleted lines starting with an action verb
or an "Action:"/"TODO:" prefix become one candidate commitment. An LLM-narrated
refinement can layer on top in a later phase — the extractor's contract stays the same
so both paths return the same schema.

The extractor NEVER invents a due date or owner. If the notes didn't say, the fields
stay null and the reviewer fills them on the confirmation screen.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.models_p2 import SupervisionCommitment


ACTION_VERBS = (
    "review", "share", "prepare", "submit", "draft", "send", "schedule",
    "confirm", "book", "read", "check", "arrange", "circulate", "write",
    "produce", "update", "attend", "follow up", "follow-up",
)

_LINE_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*(?P<body>.+)$", re.IGNORECASE | re.MULTILINE)
_ACTION_PREFIX_RE = re.compile(r"^\s*(?:action|todo|to do|next step)\s*[:\-]\s*(?P<body>.+)$",
                                re.IGNORECASE | re.MULTILINE)
# "by" was deliberately dropped from the keyword set — "Submit X by: Friday" is a
# deadline, not an owner, and the bare word "by" can't tell the two apart. Testing
# against real meeting-note phrasing showed it silently mislabelling due dates as
# people's names (e.g. owner_person_or_role="Friday"). "owner" / "assigned to" are
# unambiguous, so we keep only those.
_OWNER_RE = re.compile(r"(?:owner|assigned to)\s*[:\-]\s*(?P<owner>[A-Za-z .'\-]{2,60})",
                        re.IGNORECASE)


def _candidates(notes: str) -> list[dict[str, Any]]:
    """Deterministic sweep — returns text + optional owner hint per candidate line."""
    if not notes:
        return []
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for regex in (_ACTION_PREFIX_RE, _LINE_RE):
        for m in regex.finditer(notes):
            body = m.group("body").strip()
            if not body or body in seen:
                continue
            first_word = body.split()[0].lower().rstrip(":,;")
            starts_with_verb = any(body.lower().startswith(v) for v in ACTION_VERBS)
            if regex is _LINE_RE and not starts_with_verb:
                # A bulleted line that isn't a verb-led action isn't a commitment.
                continue
            owner_match = _OWNER_RE.search(body)
            owner = owner_match.group("owner").strip() if owner_match else None
            # Trim owner-hint suffix off the text so it isn't duplicated.
            text = _OWNER_RE.sub("", body).strip(" .,;")
            out.append({"text": text, "owner_person_or_role": owner})
            seen.add(body)
            _ = first_word  # kept for future prioritisation
    return out


class CommitmentExtractor:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def propose(self, meeting_id: uuid.UUID, student_id: uuid.UUID,
                       notes: str) -> list[dict[str, Any]]:
        """Return proposed commitments — the caller confirms before persistence."""
        return _candidates(notes)

    async def persist_confirmed(
        self, meeting_id: uuid.UUID, student_id: uuid.UUID,
        confirmed: list[dict[str, Any]], confirmed_by_user_id: uuid.UUID | None,
    ) -> list[SupervisionCommitment]:
        """Persist the reviewer-confirmed commitments as source-of-truth rows."""
        now = datetime.now(timezone.utc)
        rows: list[SupervisionCommitment] = []
        for c in confirmed:
            row = SupervisionCommitment(
                meeting_id=meeting_id,
                student_id=student_id,
                text=(c.get("text") or "").strip()[:1000],
                owner_person_or_role=c.get("owner_person_or_role"),
                due_at=c.get("due_at"),
                dependency_ids=c.get("dependency_ids"),
                status="open",
                source=c.get("source") or "extractor",
                confirmed_by_user_id=confirmed_by_user_id,
                confirmed_at=now,
            )
            self.session.add(row)
            rows.append(row)
        await self.session.flush()
        return rows
