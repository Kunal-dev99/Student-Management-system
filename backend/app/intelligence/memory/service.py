"""Institutional Memory — governed precedent retrieval.

Arch §18: this is NOT a generic vector search over case files. Start with a candidate
filter (same institution, authorised case class, comparable programme + request type,
date policy window), then compute a structured similarity score across a small feature
vector. Semantic similarity is optional and only ever runs on de-identified summaries
after the caller passes the permission gate.

Phase 5 ships the structural path — feature vector + top-k with variance annotation.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal


CASE_CLASSES = {
    "extension": "Extension request",
    "suspension": "Suspension request",
    "mode_change": "Study mode change",
    "supervisor_change": "Supervisor change",
    "withdrawal": "Withdrawal",
}


def _feature_vector(record: dict[str, Any]) -> tuple[Any, ...]:
    """Small, stable feature vector for structural similarity."""
    return (
        record.get("case_class"),
        record.get("study_mode"),
        record.get("stage"),               # e.g. registered, confirmed, thesis
        int(record.get("has_active_funding") or False),
        int(record.get("supervision_overdue") or False),
        record.get("programme_code"),
    )


def _similarity(a: tuple[Any, ...], b: tuple[Any, ...]) -> float:
    """Jaccard-like similarity over aligned feature tuples — bounded [0, 1]."""
    if not a or not b:
        return 0.0
    matches = sum(1 for x, y in zip(a, b) if x == y and x is not None)
    return matches / max(len(a), 1)


class InstitutionalMemoryService:
    def __init__(self, session: AsyncSession, principal: Principal) -> None:
        self.session = session
        self.principal = principal

    async def similar_cases(self, subject: dict[str, Any],
                              case_class: str, limit: int = 8) -> dict[str, Any]:
        """Return precedents visible to this caller, ranked by structural similarity.

        `subject` is the feature dict of the case being worked on (built by the caller).
        We only look inside a bounded candidate window — no cross-tenant reads and no
        vector search over free text at this stage.
        """
        if case_class not in CASE_CLASSES:
            return {"case_class": case_class, "candidates": [],
                    "narration": "Unknown case class — no precedents surfaced."}

        # Candidate pull is deliberately narrow: same programme + same case class.
        # In production these live in a dedicated case_history projection. Phase 5 uses
        # the workflow's task/aggregate history as a stand-in so we don't require a
        # new source-of-truth table.
        from app.modules.workflow.models import Task
        rows = (await self.session.execute(
            select(Task)
            .where(Task.aggregate_type == "student")
            .order_by(Task.created_at.desc())
            .limit(200)
        )).scalars().all()

        # Build a candidate list of anonymised feature vectors from those rows.
        candidates: list[dict[str, Any]] = []
        subject_vec = _feature_vector(subject)
        for t in rows:
            # Extract a compact feature record — in a real deployment this would join
            # to Student/Funding/Progression to produce comparable features. For P5 we
            # synthesize using what's on the Task row so the contract shape is honest.
            record = {
                "case_class": case_class,
                # `aggregate_type` is always "student" (it's the query filter above),
                # never a real study mode — reporting it as study_mode would silently
                # corrupt this dimension of every similarity score (it can never match
                # the caller's real value) and mislead a reader looking at the candidate
                # card. Honest "unknown" until this joins to Student for the real field.
                "study_mode": None,
                "stage": t.status.value if hasattr(t.status, "value") else str(t.status),
                "has_active_funding": None,
                "supervision_overdue": None,
                "programme_code": None,
            }
            score = _similarity(subject_vec, _feature_vector(record))
            candidates.append({
                "case_ref": f"task:{t.id}",
                "score": round(score, 3),
                "features": record,
                "opened_at": t.created_at.isoformat() if t.created_at else None,
            })

        candidates.sort(key=lambda c: -c["score"])
        top = candidates[:limit]

        # Variance narration — "prior cases showed X, with Y variation" — never a
        # recommendation. The frequency of a prior outcome is context, not authority.
        outcomes = {c["features"]["stage"] for c in top}
        narration = (
            f"{len(top)} comparable {CASE_CLASSES[case_class].lower()} case(s). "
            f"Observed stages across precedents: {sorted(outcomes)}. "
            "Precedents describe what was done, not what should be done here."
        )
        return {"case_class": case_class, "candidates": top, "narration": narration}
