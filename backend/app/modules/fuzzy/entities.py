"""Row-scoped fuzzy entity resolver.

Given a normalised query, extract the entities the caller can actually see. Never
returns a person the caller has no permission to view — that would leak identities
via search-as-you-type.

Uses `rapidfuzz` for token-set matching; falls back to plain lowercase substring
when rapidfuzz is unavailable so tests can run in constrained envs.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal
from app.modules.person.models import Person
from app.modules.student_record.models import Student


try:
    from rapidfuzz import fuzz  # type: ignore
    _HAVE_RAPIDFUZZ = True
except ImportError:                # pragma: no cover — CI installs rapidfuzz
    _HAVE_RAPIDFUZZ = False


STUDENT_REF_RE = re.compile(r"\b([A-Za-z]{2,6}[-_/]?\d{2,8})\b")


@dataclass(frozen=True)
class ResolvedEntity:
    kind: str                # "student" | "person"
    id: str                  # uuid as string
    name: str
    student_ref: str | None
    score: float             # 0..1


def _ratio(query: str, candidate: str) -> float:
    if not candidate:
        return 0.0
    if _HAVE_RAPIDFUZZ:
        return fuzz.token_set_ratio(query, candidate) / 100.0
    # Deterministic fallback: substring gives 1.0, else Jaccard on tokens.
    q_tokens = set(query.lower().split())
    c_tokens = set(candidate.lower().split())
    if not q_tokens or not c_tokens:
        return 0.0
    if candidate.lower() in query.lower() or query.lower() in candidate.lower():
        return 1.0
    inter = len(q_tokens & c_tokens)
    union = len(q_tokens | c_tokens)
    return inter / union if union else 0.0


async def _allowed_student_ids(principal: Principal, session: AsyncSession) -> list[uuid.UUID] | None:
    """Reuse the same row-scoping helper the rest of the assistant already uses."""
    from app.modules.student_record.router import scoped_ids
    return await scoped_ids(principal, session)


async def resolve_entities(
    query: str, principal: Principal, session: AsyncSession,
    *, limit: int = 5, min_score: float = 0.55,
) -> list[ResolvedEntity]:
    """Match names / student refs against everyone the caller can see. Ordered by score."""
    q = (query or "").strip()
    if not q:
        return []

    # 1) Student refs match unambiguously — take the first ref found and try it exact.
    ref_hit: str | None = None
    m = STUDENT_REF_RE.search(q)
    if m:
        ref_hit = m.group(1)

    allowed = await _allowed_student_ids(principal, session)

    # 2) Pull the caller-visible slice of Student+Person. On institutional scale this is
    #    bounded by allowed_ids; if unbounded (admin) we still cap the fetch to keep the
    #    resolver O(1) per request.
    stmt = select(Student, Person).join(Person, Person.id == Student.person_id)
    if allowed is not None:
        stmt = stmt.where(Student.id.in_(allowed))
    if ref_hit:
        stmt = stmt.where(
            or_(Student.student_ref.ilike(ref_hit),
                Student.student_ref.ilike(f"%{ref_hit}%"))
        )
    rows = (await session.execute(stmt.limit(500))).all()

    if ref_hit and rows:
        row = rows[0]
        stu, per = row
        return [ResolvedEntity(
            kind="student", id=str(stu.id),
            name=f"{per.given_name} {per.family_name}",
            student_ref=stu.student_ref, score=1.0,
        )]

    # 3) Fuzzy name match: score each candidate against the raw query and keep the winners.
    scored: list[ResolvedEntity] = []
    for stu, per in rows:
        full = f"{per.given_name} {per.family_name}"
        score = _ratio(q, full)
        # A first-name-only hit is common ("alice's payments"). Boost the given name too.
        given_score = _ratio(q, per.given_name or "")
        score = max(score, given_score * 0.9)
        if score >= min_score:
            scored.append(ResolvedEntity(
                kind="student", id=str(stu.id),
                name=full, student_ref=stu.student_ref, score=score,
            ))

    scored.sort(key=lambda e: (-e.score, e.name))
    return scored[:limit]
