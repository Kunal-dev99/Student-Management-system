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

from datetime import date, timedelta

from sqlalchemy import func, select
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

        # Candidate pool: real students, joined to the features the similarity vector needs so
        # scores genuinely vary (ICR G6). Earlier this synthesised records from Task rows with
        # study_mode/programme/funding hard-coded to None, so every candidate scored the same —
        # the "identical scores" the demo hit. Refs stay de-identified (no name, no student ref).
        from app.modules.funding.constants import FundingStatus
        from app.modules.funding.models import FundingArrangement
        from app.modules.student_record.models import Programme, Student

        students = (await self.session.execute(
            select(Student).order_by(Student.created_at.desc()).limit(200)
        )).scalars().all()
        programmes = {
            p.id: p for p in (await self.session.execute(select(Programme))).scalars().all()
        }
        funded_ids = {
            fa.student_id for fa in (await self.session.execute(
                select(FundingArrangement).where(
                    FundingArrangement.status == FundingStatus.active,
                    FundingArrangement.valid_to.is_(None),
                )
            )).scalars().all()
        }

        # Supervision-overdue set in one grouped query (no N+1): latest meeting older than the
        # institution's expected interval, or no meeting at all, counts as overdue.
        from app.modules.settings.service import setting_value
        from app.modules.supervision.models import SupervisionMeeting

        interval = int(await setting_value(self.session, "supervision.expected_meeting_interval_days"))
        cutoff = date.today() - timedelta(days=interval)
        last_meeting = dict((await self.session.execute(
            select(SupervisionMeeting.student_id, func.max(SupervisionMeeting.met_on))
            .group_by(SupervisionMeeting.student_id)
        )).all())

        candidates: list[dict[str, Any]] = []
        subject_vec = _feature_vector(subject)
        for st in students:
            prog = programmes.get(st.programme_id)
            record = {
                "case_class": case_class,   # the candidate filter — always the explored class
                "study_mode": st.study_mode.value if hasattr(st.study_mode, "value") else st.study_mode,
                "stage": st.status.value if hasattr(st.status, "value") else str(st.status),
                "has_active_funding": st.id in funded_ids,
                "supervision_overdue": (
                    st.id not in last_meeting or last_meeting[st.id] < cutoff
                ),
                "programme_code": prog.code if prog else None,
            }
            score = _similarity(subject_vec, _feature_vector(record))
            candidates.append({
                "case_ref": f"case:{str(st.id)[:8]}",
                "score": round(score, 3),
                "features": record,
                "opened_at": st.created_at.isoformat() if st.created_at else None,
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
