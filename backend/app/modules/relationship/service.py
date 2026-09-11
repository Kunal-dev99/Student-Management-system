"""Relationship signal — evidence assembly + classification.

Deterministic core reads the last 90 days of messages + supervision meeting notes for the
(student, supervisor) pair, packs them into a compact prompt, and hands them to the
Classify shape from the AI layer. The label the model returns is bounded to four options;
if the model refuses or is unavailable, the fallback runs keyword rules over the same
evidence.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.classify import classify as ai_classify
from app.ai.types import ClassifyResult
from app.modules.portal.models import PortalMessage
from app.modules.supervision.models import SupervisionMeeting


LOOKBACK_DAYS = 90
MAX_EVIDENCE_ITEMS = 20


LABELS = ["thriving", "steady", "drifting", "strained"]


# Keyword rules for the fallback classifier. Order matters — first match wins.
FALLBACK_RULES: dict[str, list[str]] = {
    "strained": [
        "frustrated", "frustration", "unresponsive", "not responding",
        "not received", "no reply", "third time", "disappointed",
        "conflict", "unhappy", "concerned about",
    ],
    "drifting": [
        "missed", "cancelled", "postponed", "reschedule", "sorry i",
        "overdue", "late", "delayed", "haven't heard", "chase",
        "haven't done", "behind",
    ],
    "thriving": [
        "great progress", "went well", "delighted", "excellent",
        "well done", "brilliant", "on track", "ahead of schedule",
        "really good", "impressed",
    ],
    "steady": [
        "steady", "on schedule", "as planned", "as agreed", "coming along",
    ],
}


@dataclass
class EvidenceItem:
    kind: str            # "message" | "meeting"
    at: datetime
    author: str          # "student" | "supervisor" | "meeting"
    text: str            # truncated body


@dataclass
class RelationshipSignal:
    """The final signal: label + reasoning + the evidence it saw."""

    student_id: str
    supervisor_person_id: str
    label: str
    reasoning: str
    provenance_source: str
    provenance_model: str | None
    evidence: list[EvidenceItem]
    evidence_totals: dict[str, int]  # {"messages": N, "meetings": M}


async def _assemble_evidence(
    session: AsyncSession,
    student_id: uuid.UUID,
    supervisor_person_id: uuid.UUID,
) -> list[EvidenceItem]:
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    messages = (await session.execute(
        select(PortalMessage)
        .where(
            PortalMessage.student_id == student_id,
            PortalMessage.supervisor_person_id == supervisor_person_id,
            PortalMessage.created_at >= since,
        )
        .order_by(PortalMessage.created_at.asc())
    )).scalars().all()

    meetings = (await session.execute(
        select(SupervisionMeeting)
        .where(
            SupervisionMeeting.student_id == student_id,
            SupervisionMeeting.met_on >= since.date(),
        )
        .order_by(SupervisionMeeting.met_on.asc())
    )).scalars().all()

    def _aware(dt: datetime | None) -> datetime:
        """Postgres returns tz-aware datetimes; SQLite (tests) returns naive. Normalise
        so the sort below never compares aware to naive and crashes with a TypeError."""
        if dt is None:
            return since
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    items: list[EvidenceItem] = []
    for m in messages:
        items.append(EvidenceItem(
            kind="message",
            at=_aware(m.created_at),
            author=m.author_role,
            text=(m.body or "")[:400],
        ))
    for meet in meetings:
        # Prefer notes + actions; fall back to a placeholder.
        text_parts: list[str] = []
        if meet.notes:
            text_parts.append(f"NOTES: {meet.notes.strip()}")
        if meet.actions:
            text_parts.append(f"ACTIONS: {meet.actions.strip()}")
        blob = " · ".join(text_parts) or "(meeting recorded; no notes)"
        items.append(EvidenceItem(
            kind="meeting",
            at=datetime.combine(meet.met_on, datetime.min.time(), tzinfo=timezone.utc),
            author="meeting",
            text=blob[:600],
        ))

    items.sort(key=lambda x: x.at)
    # Keep the most recent MAX_EVIDENCE_ITEMS so the prompt stays tight.
    return items[-MAX_EVIDENCE_ITEMS:]


def _prompt_text(items: list[EvidenceItem]) -> str:
    """Compact chronological transcript for the classifier."""
    if not items:
        return "(no messages or meeting notes in the last 90 days)"
    lines: list[str] = []
    for it in items:
        stamp = it.at.date().isoformat()
        prefix = {
            "student": "STUDENT",
            "supervisor": "SUPERVISOR",
            "meeting": "MEETING",
        }.get(it.author, it.author.upper())
        lines.append(f"[{stamp}] {prefix}: {it.text}")
    return "\n".join(lines)


async def signal_for_pair(
    session: AsyncSession,
    student_id: uuid.UUID,
    supervisor_person_id: uuid.UUID,
) -> RelationshipSignal:
    """End-to-end: assemble evidence for the pair, classify, return the signal."""
    evidence = await _assemble_evidence(session, student_id, supervisor_person_id)

    message_count = sum(1 for i in evidence if i.kind == "message")
    meeting_count = sum(1 for i in evidence if i.kind == "meeting")

    # No history — return "steady" as the honest default rather than pretending to know.
    if not evidence:
        return RelationshipSignal(
            student_id=str(student_id),
            supervisor_person_id=str(supervisor_person_id),
            label="steady",
            reasoning="No messages or meeting notes in the last 90 days to read from.",
            provenance_source="fallback",
            provenance_model=None,
            evidence=[],
            evidence_totals={"messages": 0, "meetings": 0},
        )

    result: ClassifyResult = await ai_classify(
        text=_prompt_text(evidence),
        labels=LABELS,
        keyword_rules=FALLBACK_RULES,
        fallback_label="steady",
        context=(
            "Classify the trajectory of a supervisor–student relationship from the "
            "recent messages and meeting notes. Look for tone shifts, responsiveness, "
            "and specific concerns. 'Strained' = active conflict or breakdown. "
            "'Drifting' = missed things, delayed replies, quiet distance. "
            "'Thriving' = clear positive momentum. 'Steady' = business as usual. "
            "Prefer 'steady' when the evidence is thin or ambiguous."
        ),
    )

    return RelationshipSignal(
        student_id=str(student_id),
        supervisor_person_id=str(supervisor_person_id),
        label=result.label,
        reasoning=result.reasoning,
        provenance_source=result.provenance.source,
        provenance_model=result.provenance.model,
        evidence=evidence,
        evidence_totals={"messages": message_count, "meetings": meeting_count},
    )
