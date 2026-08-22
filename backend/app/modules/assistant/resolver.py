"""Entity resolution (Phase 5.1).

LLMs hallucinate UUIDs, so no tool ever accepts an id the model invented. Names resolve here,
against the caller's *scoped* view, and ambiguity is returned to be asked about rather than guessed.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.person.models import Person
from app.modules.student_record.models import Student

STUDENT_REF_RE = re.compile(r"\bPGR-\d{4}-[A-Z0-9]+\b", re.IGNORECASE)


class Resolver:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_students(
        self, query: str, *, allowed_ids: list[uuid.UUID] | None = None, limit: int = 8
    ) -> list[dict]:
        """Match on student ref or person name. Returns candidates, never a guess."""
        q = (query or "").strip()
        stmt = select(Student, Person).join(Person, Person.id == Student.person_id)
        if allowed_ids is not None:
            stmt = stmt.where(Student.id.in_(allowed_ids))

        ref_match = STUDENT_REF_RE.search(q)
        if ref_match:
            stmt = stmt.where(Student.student_ref.ilike(ref_match.group(0)))
        elif q:
            like = f"%{q}%"
            stmt = stmt.where(
                (Person.given_name + " " + Person.family_name).ilike(like)
                | Person.given_name.ilike(like)
                | Person.family_name.ilike(like)
                | Student.student_ref.ilike(like)
            )
        rows = (await self.session.execute(stmt.limit(limit))).all()
        return [
            {
                "studentId": str(s.id),
                "studentRef": s.student_ref,
                "personName": f"{p.given_name} {p.family_name}",
                "status": s.status.value if hasattr(s.status, "value") else s.status,
                "link": f"/students/{s.id}",
            }
            for s, p in rows
        ]

    async def find_people(self, query: str, limit: int = 8) -> list[dict]:
        like = f"%{(query or '').strip()}%"
        rows = (await self.session.execute(
            select(Person).where(
                (Person.given_name + " " + Person.family_name).ilike(like)
                | Person.given_name.ilike(like)
                | Person.family_name.ilike(like)
            ).limit(limit)
        )).scalars().all()
        return [
            {"personId": str(p.id), "personName": f"{p.given_name} {p.family_name}", "link": f"/persons/{p.id}"}
            for p in rows
        ]

    @staticmethod
    def disambiguation(candidates: list[dict], what: str = "student") -> dict | None:
        """Return a 'needs clarification' payload when a reference is not unique."""
        if len(candidates) == 1:
            return None
        if not candidates:
            return {"resolved": False, "reason": f"No {what} matched.", "candidates": []}
        return {
            "resolved": False,
            "reason": f"Several {what}s match — which one?",
            "candidates": candidates,
        }
