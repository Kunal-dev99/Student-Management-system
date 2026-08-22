"""Supervisor matching and the research relationship graph (Phase 7, item R5).

Two capabilities the gap analysis rated MEDIUM — enhancements, not gaps:

1. **Matching** — suggest supervisors for a research proposal or an advertised position, with an
   **explainable score**: every point is attributed to a named reason a human can check and argue
   with. No embeddings, no model. The gap analysis suggested sentence-transformers; that would add
   a very large dependency to rank a few dozen academics against a bounded vocabulary of research
   areas, and — decisively — it would make the score unexplainable. A supervisor allocation is a
   decision people contest, so "why was I not suggested?" must have an answer.

2. **Relationship graph** — Person ↔ Research ↔ Supervisor ↔ Award ↔ Funding as nodes and edges,
   so the connections that are implicit across six tables can be seen at once.

Both respect row scoping and add no dependencies.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.person.models import Person
from app.modules.research.models import ResearchAward
from app.modules.student_record.models import ResearchArea, ResearchProject, Student
from app.modules.supervision.models import SupervisorRelationship

# Scoring weights. Deliberately small integers that sum to 100 so a score reads as a percentage
# and the contribution of each factor is obvious.
W_AREA_EXACT = 45        # supervises in exactly this research area
W_KEYWORD = 25           # proposal words overlap their students' topics
W_CAPACITY = 20          # has room to take someone on
W_TRACK_RECORD = 10      # has completed supervisions

STOPWORDS = {
    "a", "an", "the", "of", "for", "and", "or", "in", "on", "to", "with", "using", "study",
    "research", "analysis", "investigation", "towards", "into", "via", "by", "at", "from",
    "this", "that", "based", "novel", "new", "approach", "method", "methods", "phd",
}


def _keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in STOPWORDS}


class MatchingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Supervisor matching
    # ------------------------------------------------------------------

    async def suggest_supervisors(
        self,
        *,
        research_area_id: uuid.UUID | None = None,
        proposal_text: str | None = None,
        max_supervisees: int | None = None,
        limit: int = 10,
    ) -> dict:
        """Rank supervisors for a proposal or position, showing why each scored what it did."""
        if max_supervisees is None:
            from app.modules.settings.service import setting_value

            max_supervisees = await setting_value(self.session, "supervision.max_supervisees")
        if research_area_id is None and not (proposal_text or "").strip():
            return {"criteria": {}, "suggestions": [],
                    "note": "Provide a research area, a proposal, or both."}

        area_name = None
        if research_area_id:
            area = (await self.session.execute(
                select(ResearchArea).where(ResearchArea.id == research_area_id)
            )).scalar_one_or_none()
            if area is None:
                raise NotFoundError("Research area not found")
            area_name = area.name

        # Only the *proposal* contributes topic keywords. Deriving them from the area name too
        # double-counts: a search for "Machine Learning" would award +45 for the area and another
        # +16 for the topics "machine, learning" — the same signal twice, which flattens the
        # ranking between supervisors who differ in what they actually work on. Topic overlap has
        # to be independent evidence or it is not evidence.
        wanted = _keywords(proposal_text or "") - _keywords(area_name or "")

        # Every current supervision relationship, with the student's area and project topic.
        rows = (await self.session.execute(
            select(SupervisorRelationship, Student, ResearchProject)
            .join(Student, Student.id == SupervisorRelationship.student_id)
            .join(ResearchProject, ResearchProject.student_id == Student.id, isouter=True)
        )).all()

        profile: dict[uuid.UUID, dict] = {}
        for rel, student, project in rows:
            p = profile.setdefault(rel.supervisor_person_id, {
                "current": 0, "completed": 0, "areas": set(), "topics": set(),
            })
            if rel.valid_to is None:
                p["current"] += 1
            else:
                p["completed"] += 1
            if student.research_area_id:
                p["areas"].add(student.research_area_id)
            if project and project.research_topic:
                p["topics"] |= _keywords(project.research_topic)

        # Anyone who has ever supervised is a candidate.
        if not profile:
            return {"criteria": {"researchArea": area_name, "keywords": sorted(wanted)},
                    "suggestions": [],
                    "note": "No supervision history exists yet, so no one can be ranked."}

        people = {
            p.id: p for p in (await self.session.execute(
                select(Person).where(Person.id.in_(list(profile)))
            )).scalars().all()
        }

        suggestions = []
        for person_id, p in profile.items():
            person = people.get(person_id)
            if person is None:
                continue
            score, reasons = 0, []

            if research_area_id and research_area_id in p["areas"]:
                score += W_AREA_EXACT
                reasons.append({"factor": "research area", "points": W_AREA_EXACT,
                                "detail": f"already supervises in {area_name}"})

            overlap = wanted & p["topics"]
            if overlap:
                pts = min(W_KEYWORD, len(overlap) * 8)
                score += pts
                reasons.append({"factor": "topic overlap", "points": pts,
                                "detail": "shared terms: " + ", ".join(sorted(overlap)[:5])})

            free = max_supervisees - p["current"]
            if free > 0:
                pts = round(W_CAPACITY * min(1.0, free / max(1, max_supervisees / 2)))
                score += pts
                reasons.append({"factor": "capacity", "points": pts,
                                "detail": f"{p['current']}/{max_supervisees} supervisees — room for {free} more"})
            else:
                reasons.append({"factor": "capacity", "points": 0,
                                "detail": f"at capacity ({p['current']}/{max_supervisees})"})

            if p["completed"]:
                pts = min(W_TRACK_RECORD, p["completed"] * 5)
                score += pts
                reasons.append({"factor": "track record", "points": pts,
                                "detail": f"{p['completed']} completed supervision(s)"})

            suggestions.append({
                "personId": str(person_id),
                "personName": f"{person.given_name} {person.family_name}",
                "score": score,
                "currentSupervisees": p["current"],
                "atCapacity": free <= 0,
                "reasons": reasons,
                "link": f"/persons/{person_id}",
            })

        # Ties are common when only an area is given (everyone scores area + capacity), and the
        # capacity band is deliberately coarse. Break the tie on who actually has more room
        # before falling back to name, so the order is useful rather than merely alphabetical.
        suggestions.sort(key=lambda x: (-x["score"], x["currentSupervisees"], x["personName"]))
        return {
            "criteria": {"researchArea": area_name, "keywords": sorted(wanted),
                         "maxSupervisees": max_supervisees},
            "suggestions": suggestions[:limit],
            "note": "Scores are advisory and fully explained. A supervisor at capacity is still "
                    "listed, scored down rather than hidden, so the decision stays with a human.",
        }

    # ------------------------------------------------------------------
    # Relationship graph
    # ------------------------------------------------------------------

    async def relationship_graph(
        self, *, student_id: uuid.UUID | None = None, award_id: uuid.UUID | None = None,
        allowed_ids: list[uuid.UUID] | None = None, limit: int = 40,
    ) -> dict:
        """Nodes and edges for Person ↔ Research ↔ Supervisor ↔ Award ↔ Funding.

        Centre it on one student or one award, or omit both for a bounded overview.
        """
        from app.modules.funding.constants import FundingStatus
        from app.modules.funding.models import FundingArrangement, FundingSource

        stmt = select(Student, Person).join(Person, Person.id == Student.person_id)
        if student_id:
            stmt = stmt.where(Student.id == student_id)
        if allowed_ids is not None:
            stmt = stmt.where(Student.id.in_(allowed_ids))
        student_rows = (await self.session.execute(stmt.limit(limit))).all()
        if not student_rows:
            return {"nodes": [], "edges": [], "note": "Nothing in scope to draw."}

        ids = [st.id for st, _ in student_rows]
        projects = {p.student_id: p for p in (await self.session.execute(
            select(ResearchProject).where(ResearchProject.student_id.in_(ids))
        )).scalars().unique().all()}
        arrangements = list((await self.session.execute(
            select(FundingArrangement).where(
                FundingArrangement.student_id.in_(ids),
                FundingArrangement.status == FundingStatus.active,
            )
        )).scalars().all())
        rels = list((await self.session.execute(
            select(SupervisorRelationship).where(
                SupervisorRelationship.student_id.in_(ids),
                SupervisorRelationship.valid_to.is_(None),
            )
        )).scalars().all())

        award_ids = {p.research_award_id for p in projects.values() if p.research_award_id}
        award_ids |= {a.research_award_id for a in arrangements if a.research_award_id}
        if award_id:
            award_ids.add(award_id)
        awards = {a.id: a for a in (await self.session.execute(
            select(ResearchAward).where(ResearchAward.id.in_(list(award_ids)))
        )).scalars().all()} if award_ids else {}

        funder_ids = {a.funder_id for a in awards.values() if a.funder_id}
        funder_ids |= {a.funding_source_id for a in arrangements if a.funding_source_id}
        funders = {f.id: f for f in (await self.session.execute(
            select(FundingSource).where(FundingSource.id.in_(list(funder_ids)))
        )).scalars().all()} if funder_ids else {}

        supervisor_ids = {r.supervisor_person_id for r in rels}
        supervisors = {p.id: p for p in (await self.session.execute(
            select(Person).where(Person.id.in_(list(supervisor_ids)))
        )).scalars().all()} if supervisor_ids else {}

        nodes: dict[str, dict] = {}
        edges: list[dict] = []

        def node(kind: str, key, label: str, **extra) -> str:
            nid = f"{kind}:{key}"
            if nid not in nodes:
                nodes[nid] = {"id": nid, "kind": kind, "label": label, **extra}
            return nid

        for student, person in student_rows:
            sn = node("student", student.id, f"{person.given_name} {person.family_name}",
                      sub=student.student_ref, link=f"/students/{student.id}",
                      status=student.status.value if hasattr(student.status, "value") else student.status)
            proj = projects.get(student.id)
            if proj:
                pn = node("project", proj.id, proj.research_topic or "Research project")
                edges.append({"source": sn, "target": pn, "label": "researches"})
                if proj.research_award_id and proj.research_award_id in awards:
                    aw = awards[proj.research_award_id]
                    an = node("award", aw.id, aw.award_ref, sub=aw.title)
                    edges.append({"source": pn, "target": an, "label": "under"})
            for r in rels:
                if r.student_id != student.id:
                    continue
                sup = supervisors.get(r.supervisor_person_id)
                if sup is None:
                    continue
                vn = node("supervisor", sup.id, f"{sup.given_name} {sup.family_name}",
                          link=f"/persons/{sup.id}")
                edges.append({"source": vn, "target": sn,
                              "label": r.role.value if hasattr(r.role, "value") else r.role})
            for a in arrangements:
                if a.student_id != student.id:
                    continue
                fn = node("funding", a.id,
                          a.funding_type.value if hasattr(a.funding_type, "value") else "funding",
                          sub=f"{a.currency or ''} {a.stipend_amount or ''}".strip())
                edges.append({"source": fn, "target": sn, "label": "funds"})
                if a.research_award_id and a.research_award_id in awards:
                    aw = awards[a.research_award_id]
                    edges.append({"source": node("award", aw.id, aw.award_ref, sub=aw.title),
                                  "target": fn, "label": "pays for"})
                if a.funding_source_id and a.funding_source_id in funders:
                    f = funders[a.funding_source_id]
                    edges.append({"source": node("funder", f.id, f.name), "target": fn,
                                  "label": "provides"})

        for aw in awards.values():
            if aw.funder_id and aw.funder_id in funders:
                f = funders[aw.funder_id]
                edges.append({"source": node("funder", f.id, f.name),
                              "target": node("award", aw.id, aw.award_ref, sub=aw.title),
                              "label": "awards"})

        # De-duplicate edges (a funder can reach a student by several paths).
        seen, unique_edges = set(), []
        for e in edges:
            key = (e["source"], e["target"], e["label"])
            if key not in seen:
                seen.add(key)
                unique_edges.append(e)

        return {
            "nodes": list(nodes.values()),
            "edges": unique_edges,
            "counts": {"nodes": len(nodes), "edges": len(unique_edges),
                       "students": len(student_rows)},
        }
