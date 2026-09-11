"""Weekly review queue — deterministic candidate build + AI rank orchestration.

The candidate list is what the app would show if there were no model at all — it's an
ordinary, sortable table of at-risk students with a rule-based priority score. The AI
layer only picks top N with one sentence of reasoning per pick, and the whole candidate
table travels back with the picks so the UI can render it beside.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rank import rank as ai_rank
from app.ai.types import Candidate, RankResult
from app.modules.funding.constants import FundingStatus
from app.modules.funding.models import FundingArrangement
from app.modules.progression.constants import MilestoneStatus
from app.modules.progression.models import Milestone
from app.modules.student_record.constants import StudentStatus
from app.modules.student_record.models import Student
from app.modules.person.models import Person


ACTIVE = {StudentStatus.registered, StudentStatus.active}


@dataclass(frozen=True)
class QueueRow:
    """One row in the deterministic queue. Rendered as a table beside the AI picks."""

    student_id: str
    student_ref: str
    person_name: str
    score: float
    reasons: list[str]


@dataclass(frozen=True)
class WeeklyQueue:
    """A ranked pick + the full deterministic table it was drawn from."""

    picks: RankResult
    candidates: list[QueueRow]


_CANDIDATE_CACHE: dict[str, tuple[float, list[QueueRow]]] = {}
_CACHE_TTL_SECONDS = 30.0


async def build_candidates(session: AsyncSession, today: date | None = None) -> list[QueueRow]:
    """Score every active student on risk signals. Deterministic — no model.

    Cached in-memory for 30 seconds. Risk signals change on the order of hours or days
    (a milestone becoming overdue, a funding arrangement ending), so a 30s TTL keeps a
    quick re-open of the page or a rapid "Run again" essentially free while still picking
    up real changes within a supervisor's session.
    """
    today = today or date.today()
    cache_key = today.isoformat()
    hit = _CANDIDATE_CACHE.get(cache_key)
    if hit is not None and (time.monotonic() - hit[0]) < _CACHE_TTL_SECONDS:
        return hit[1]

    student_rows = (
        await session.execute(select(Student, Person).join(Person, Person.id == Student.person_id))
    ).all()

    overdue_by_student: dict[str, int] = {}
    for milestone in (await session.execute(select(Milestone))).scalars().all():
        if milestone.status == MilestoneStatus.overdue:
            sid = str(milestone.student_id)
            overdue_by_student[sid] = overdue_by_student.get(sid, 0) + 1

    funded_students: set[str] = set()
    for fa in (await session.execute(select(FundingArrangement))).scalars().all():
        if fa.status == FundingStatus.active:
            funded_students.add(str(fa.student_id))

    rows: list[QueueRow] = []
    for student, person in student_rows:
        if student.status not in ACTIVE:
            continue
        student_id = str(student.id)
        reasons: list[str] = []
        score = 0.0

        overdue_count = overdue_by_student.get(student_id, 0)
        if overdue_count:
            reasons.append(f"{overdue_count} milestone(s) overdue")
            score += 40.0 + 5.0 * overdue_count

        if student_id not in funded_students:
            reasons.append("no active funding")
            score += 20.0

        # Nearing expected end date — six months out is worth attention.
        if student.expected_end_date:
            days_left = (student.expected_end_date - today).days
            if 0 <= days_left <= 180:
                reasons.append(f"expected end in {days_left} days")
                score += 15.0
            elif days_left < 0:
                reasons.append(f"past expected end by {-days_left} days")
                score += 25.0

        if not reasons:
            continue

        rows.append(QueueRow(
            student_id=student_id,
            student_ref=student.student_ref,
            person_name=f"{person.given_name} {person.family_name}",
            score=round(score, 1),
            reasons=reasons,
        ))

    rows.sort(key=lambda r: -r.score)
    _CANDIDATE_CACHE[cache_key] = (time.monotonic(), rows)
    return rows


def _to_candidates(rows: list[QueueRow]) -> list[Candidate]:
    return [
        Candidate(
            id=r.student_id,
            label=f"{r.person_name} ({r.student_ref})",
            score=r.score,
            facts={"reasons": r.reasons},
        )
        for r in rows
    ]


async def weekly_queue(session: AsyncSession, top_n: int = 5, today: date | None = None) -> WeeklyQueue:
    """Full flow: build the deterministic table, then rank top-N through the AI layer.

    The full deterministic table is returned to the caller (rendered as evidence in the
    UI), but only the top MODEL_SHORTLIST rows are sent to the model. Sending the whole
    table blows the token budget and Groq refuses the JSON — the fallback still works,
    but users see "generated offline" for the wrong reason. Capping fixes that without
    changing what the reader sees on the page.
    """
    MODEL_SHORTLIST = 10
    rows = await build_candidates(session, today)
    shortlist = rows[:MODEL_SHORTLIST]
    picks = await ai_rank(
        question=(
            "Which students need a supervisor review this week? Pick the ones whose risk "
            "flags most warrant attention now."
        ),
        candidates=_to_candidates(shortlist),
        top_n=top_n,
    )
    return WeeklyQueue(picks=picks, candidates=rows)
