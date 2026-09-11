"""Meeting-brief assembler + narrator wrapper.

Everything the paragraph mentions is produced here first as a typed structure. The AI
layer's narrator is invoked over that structure; grounding rejects any number or date it
tries to add. If the model is off, the same structure renders into a plain template.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.narrate import narrate as ai_narrate
from app.ai.types import Evidence, Narration
from app.modules.funding.constants import FundingStatus
from app.modules.funding.models import FundingArrangement
from app.modules.person.models import Person
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone, MilestoneDefinition
from app.modules.student_record.models import Student
from app.modules.supervision.models import SupervisionMeeting


@dataclass
class Change:
    """One thing that changed since the last supervisor meeting."""

    kind: str            # "milestone" | "funding" | "meeting" | "flag"
    label: str           # short human phrase — "milestone slipped", "annual review passed"
    detail: str | None = None  # secondary line — e.g. name of the milestone, the funder


@dataclass
class BriefEvidence:
    """Deterministic material the narrator paragraph must be grounded against."""

    student_id: str
    student_name: str
    student_ref: str
    last_meeting_on: date | None
    last_meeting_actions: str | None
    days_since_last: int | None
    next_meeting_on: date | None
    changes: list[Change] = field(default_factory=list)
    open_flags: list[str] = field(default_factory=list)


@dataclass
class MeetingBrief:
    """The finished brief: paragraph + the raw evidence it was drawn from."""

    evidence: BriefEvidence
    narration: Narration
    suggested_questions: list[str]


async def build_evidence(session: AsyncSession, student_id: uuid.UUID,
                         today: date | None = None) -> BriefEvidence:
    """Assemble what actually happened since the last meeting. Deterministic — no model."""
    today = today or date.today()

    row = (await session.execute(
        select(Student, Person).join(Person, Person.id == Student.person_id)
        .where(Student.id == student_id)
    )).first()
    if not row:
        raise ValueError(f"student {student_id} not found")
    student, person = row

    meetings = (await session.execute(
        select(SupervisionMeeting)
        .where(SupervisionMeeting.student_id == student_id)
        .order_by(SupervisionMeeting.met_on.desc())
    )).scalars().all()
    last = meetings[0] if meetings else None
    since = last.met_on if last else (today - timedelta(days=90))

    milestones = (await session.execute(
        select(Milestone, MilestoneDefinition)
        .join(MilestoneDefinition, MilestoneDefinition.id == Milestone.milestone_definition_id)
        .where(Milestone.student_id == student_id)
    )).all()
    fundings = (await session.execute(
        select(FundingArrangement).where(FundingArrangement.student_id == student_id)
    )).scalars().all()

    changes: list[Change] = []
    open_flags: list[str] = []

    for m, mdef in milestones:
        # Report status transitions that happened since `since`. The Milestone model does
        # not carry a status-change timestamp on this schema, so we use `updated_at` as
        # a proxy for "moved recently".
        moved_at = getattr(m, "updated_at", None)
        moved_since = moved_at.date() >= since if moved_at else False
        # `decided` covers pass/pass-with-conditions/fail/etc — the specific outcome
        # lives on the ProgressionReview record, which we don't need for the brief.
        if moved_since and m.status in (
            MilestoneStatus.decided, MilestoneStatus.submitted,
            MilestoneStatus.under_review, MilestoneStatus.overdue,
        ):
            changes.append(Change(
                kind="milestone",
                label=f"milestone {m.status.value.replace('_', ' ')}",
                detail=mdef.name,
            ))
        if m.status == MilestoneStatus.overdue:
            open_flags.append(f"{mdef.name} is overdue")

    active_funding = [f for f in fundings if f.status == FundingStatus.active]
    if not active_funding:
        open_flags.append("no active funding arrangement")
    for f in fundings:
        if f.valid_from and f.valid_from >= since and f.status == FundingStatus.active:
            changes.append(Change(kind="funding", label="funding started",
                                  detail=f.funding_type.value if f.funding_type else None))
        if f.valid_to and f.valid_to >= since and f.status != FundingStatus.active:
            changes.append(Change(kind="funding", label="funding ended",
                                  detail=f.funding_type.value if f.funding_type else None))

    if student.expected_end_date:
        days_left = (student.expected_end_date - today).days
        if 0 <= days_left <= 90:
            open_flags.append(f"expected end in {days_left} days")
        elif days_left < 0:
            open_flags.append(f"past expected end by {-days_left} days")

    # A second meeting (or later) since `since` reads as a follow-up meeting that
    # already happened — worth surfacing.
    if len(meetings) >= 2 and meetings[1].met_on and meetings[1].met_on >= since:
        pass  # `last` already captures "we did meet"; nothing extra to say.

    days_since_last = (today - last.met_on).days if last else None

    return BriefEvidence(
        student_id=str(student.id),
        student_name=f"{person.given_name} {person.family_name}",
        student_ref=student.student_ref,
        last_meeting_on=last.met_on if last else None,
        last_meeting_actions=(last.actions or None) if last else None,
        days_since_last=days_since_last,
        next_meeting_on=(last.next_meeting_on if last else None),
        changes=changes[:8],       # keep the paragraph tractable
        open_flags=open_flags[:5],
    )


def _to_evidence_payload(ev: BriefEvidence) -> Evidence:
    """Turn the typed evidence into the AI layer's `Evidence` shape (verbatim figures)."""
    figures: dict[str, str] = {}
    if ev.days_since_last is not None:
        figures["days since last meeting"] = str(ev.days_since_last)
    if ev.last_meeting_on:
        figures["last meeting date"] = ev.last_meeting_on.isoformat()
    if ev.next_meeting_on:
        figures["next meeting date"] = ev.next_meeting_on.isoformat()
    figures["change count"] = str(len(ev.changes))
    figures["open flag count"] = str(len(ev.open_flags))
    context: dict[str, object] = {
        "student": ev.student_name,
        "agreed actions from last meeting": (ev.last_meeting_actions or "none recorded"),
        "changes since": [
            {"kind": c.kind, "label": c.label, "detail": c.detail or ""}
            for c in ev.changes
        ] or "none",
        "open flags now": ev.open_flags or "none",
    }
    return Evidence(figures=figures, context=context)


def _fallback_paragraph(ev: BriefEvidence) -> str:
    """Deterministic paragraph used when the model is unavailable or ungrounded.

    Written to sound like a colleague speaking — first name, warm register, no system
    vocabulary. The AI layer polishes further, but even the plain version should read
    as human.
    """
    first = ev.student_name.split(" ")[0] if ev.student_name else "the student"
    parts: list[str] = []

    if ev.days_since_last is not None and ev.last_meeting_on:
        parts.append(
            f"You last saw {first} {ev.days_since_last} days ago "
            f"(on {ev.last_meeting_on.isoformat()})."
        )
    else:
        parts.append(f"You have no recorded prior meeting with {first}.")

    if ev.last_meeting_actions:
        parts.append(f"Then you agreed: {ev.last_meeting_actions.strip().rstrip('.')}.")

    if ev.changes:
        change_lines = [
            (c.label if not c.detail else f"{c.label} — {c.detail}")
            for c in ev.changes
        ]
        parts.append("Since then, " + "; ".join(change_lines) + ".")
    else:
        parts.append("Nothing new on record since then — worth a check-in on how things are.")

    if ev.open_flags:
        parts.append("Worth raising: " + "; ".join(ev.open_flags) + ".")

    return " ".join(parts)


def _suggested_questions(ev: BriefEvidence) -> list[str]:
    """Three deterministic prompts a supervisor could open the meeting with.

    Written the way a person would actually speak them — full grammatical questions,
    student's first name, no system vocabulary. Rule-based on purpose: "what should I
    ask?" isn't safe territory for the model to freestyle.
    """
    first_name = ev.student_name.split(" ")[0] if ev.student_name else "them"
    qs: list[str] = []

    if ev.last_meeting_actions:
        qs.append(f"How did {first_name} get on with what you agreed last time?")

    for c in ev.changes:
        if c.kind == "milestone" and "overdue" in c.label:
            qs.append(f"What's holding up the {c.detail} milestone?")
        elif c.kind == "milestone" and "submitted" in c.label:
            qs.append(f"Any feedback yet on the {c.detail} submission?")
        elif c.kind == "milestone" and "decided" in c.label:
            qs.append(f"How is {first_name} feeling about the {c.detail} outcome?")
        elif c.kind == "milestone" and "under review" in c.label:
            qs.append(f"Anything worth flagging to the {c.detail} reviewers?")
        elif c.kind == "funding" and "started" in c.label:
            qs.append(f"Is the new funding arrangement working out for {first_name}?")
        elif c.kind == "funding" and "ended" in c.label:
            qs.append(f"What's the plan now that {first_name}'s funding has ended?")
        if len(qs) >= 3:
            break

    for flag in ev.open_flags:
        if len(qs) >= 3:
            break
        if "overdue" in flag:
            qs.append(f"How can you help unblock {first_name}'s {flag.split(' is overdue')[0]}?")
        elif "no active funding" in flag:
            qs.append(f"Is {first_name} clear on the funding situation?")
        elif "expected end" in flag:
            qs.append(f"How is the plan for {first_name}'s submission window shaping up?")
        else:
            qs.append(f"Worth raising with {first_name}: {flag}.")

    if not qs:
        qs.append(f"How has the week been for {first_name}?")
        qs.append(f"Is there anything {first_name} would like your help with?")
        qs.append("Anything you want to revisit from last time?")

    return qs[:3]


async def build_brief(session: AsyncSession, student_id: uuid.UUID,
                      today: date | None = None) -> MeetingBrief:
    """End-to-end: assemble evidence, narrate, attach questions."""
    ev = await build_evidence(session, student_id, today=today)
    evidence_payload = _to_evidence_payload(ev)
    narration = await ai_narrate(
        evidence=evidence_payload,
        question=(
            "Brief a colleague on this student in two to three short sentences, warm and "
            "specific — the way a fellow supervisor would in a staff-room corridor, not "
            "how a system report would phrase it.\n"
            "\n"
            "Rules:\n"
            "- Refer to the student by first name (their full name is in the context).\n"
            "- Address the reader as 'you' — the supervisor about to walk in.\n"
            "- Name the concrete things that changed. Never say 'N changes have occurred', "
            "  '0 open flags', or 'primary item requiring attention'.\n"
            "- If nothing has changed since last time, say that plainly and suggest a check-in.\n"
            "- Skip the 'open flag' vocabulary entirely — if a flag matters, name it in "
            "  plain words (e.g. 'their annual review is overdue').\n"
            "- Do NOT narrate absences ('no pending actions', 'no flags', 'nothing else'). "
            "  If there are no flags, just don't mention flags at all.\n"
            "- End with one sentence pointing at what would be most useful to raise first. "
            "  This closing sentence MUST reference one of the concrete items already in "
            "  the evidence — a specific change, agreed action, or open flag by name. "
            "  Do NOT invent categories like 'research plan', 'upcoming milestones', "
            "  'next steps' unless those exact things appear in the evidence.\n"
            "- If there is truly nothing specific to point at, close with a general "
            "  check-in question addressed to the student by name.\n"
            "- Under 55 words. Neutral, informational tone. No exclamation, no metaphors."
        ),
        fallback_template=_fallback_paragraph(ev),
    )
    return MeetingBrief(
        evidence=ev,
        narration=narration,
        suggested_questions=_suggested_questions(ev),
    )
