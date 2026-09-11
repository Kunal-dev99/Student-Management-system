"""Duplicate finder — one scan that surfaces likely-duplicate rows across the domain.

Grouping rules are deliberately conservative: two rows are "candidate duplicates" only when
a normalised key matches exactly. Fuzzy matching (Levenshtein etc.) is deferred — a false
positive that merges two real people is far worse than a false negative you have to eyeball.

Nothing here mutates. The admin decides what to merge or delete from the UI.
"""
from __future__ import annotations

import re
import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def _norm(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s]", "", s)
    return s


async def find_duplicates(session: AsyncSession) -> dict:
    """Return duplicate candidate groups for persons, opportunities, awards, projects.

    Each group is [{id, label, sub, inUse, createdAt}, ...] with the OLDEST row first —
    that's the natural "surviving" row when merging, so the UI can pre-fill sensibly.
    """
    from app.modules.funding.models import FundingArrangement
    from app.modules.person.models import Person
    from app.modules.recruitment.models import Application, ResearchOpportunity
    from app.modules.research.models import ResearchAward
    from app.modules.student_record.models import ResearchProject, Student

    out: dict[str, list[list[dict]]] = {
        "persons": [], "opportunities": [], "awards": [], "projects": [],
    }

    # ---------- Persons ------------------------------------------------------
    person_rows = (await session.execute(
        select(Person).order_by(Person.created_at.asc())
    )).scalars().all()
    person_groups: dict[str, list[Person]] = defaultdict(list)
    email_groups: dict[str, list[Person]] = defaultdict(list)
    for p in person_rows:
        key = f"{_norm(p.given_name)}|{_norm(p.family_name)}"
        if key.strip("|"):
            person_groups[key].append(p)
        if p.email:
            email_groups[_norm(p.email)].append(p)
    # Merge the two groupings — a name match OR an email match counts.
    seen: set[uuid.UUID] = set()
    student_counts = dict((r[0], int(r[1])) for r in (await session.execute(
        select(Student.person_id, func.count()).group_by(Student.person_id)
    )).all())
    for grouping in (person_groups, email_groups):
        for members in grouping.values():
            if len(members) < 2:
                continue
            ids = tuple(sorted(str(m.id) for m in members))
            if any(uuid.UUID(i) in seen for i in ids):
                continue
            for m in members:
                seen.add(m.id)
            out["persons"].append([
                {"id": str(m.id),
                 "label": f"{m.given_name} {m.family_name}".strip(),
                 "sub": m.email or "no email",
                 "inUse": student_counts.get(m.id, 0),
                 "createdAt": m.created_at.isoformat() if m.created_at else None}
                for m in members
            ])

    # ---------- Opportunities (by normalised title) --------------------------
    opps = (await session.execute(
        select(ResearchOpportunity).order_by(ResearchOpportunity.created_at.asc())
    )).scalars().all()
    opp_groups: dict[str, list[ResearchOpportunity]] = defaultdict(list)
    for o in opps:
        k = _norm(o.title)
        if k:
            opp_groups[k].append(o)
    app_counts = dict((r[0], int(r[1])) for r in (await session.execute(
        select(Application.research_opportunity_id, func.count())
        .where(Application.research_opportunity_id.is_not(None))
        .group_by(Application.research_opportunity_id)
    )).all())
    for members in opp_groups.values():
        if len(members) < 2:
            continue
        out["opportunities"].append([
            {"id": str(m.id), "label": m.title,
             "sub": (m.status.value if hasattr(m.status, "value") else str(m.status)),
             "inUse": app_counts.get(m.id, 0),
             "createdAt": m.created_at.isoformat() if m.created_at else None}
            for m in members
        ])

    # ---------- Awards (by ref OR title) -------------------------------------
    awards = (await session.execute(
        select(ResearchAward).order_by(ResearchAward.created_at.asc())
    )).scalars().all()
    award_by_ref: dict[str, list[ResearchAward]] = defaultdict(list)
    award_by_title: dict[str, list[ResearchAward]] = defaultdict(list)
    for a in awards:
        if a.award_ref:
            award_by_ref[_norm(a.award_ref)].append(a)
        if a.title:
            award_by_title[_norm(a.title)].append(a)
    proj_counts = dict((r[0], int(r[1])) for r in (await session.execute(
        select(ResearchProject.research_award_id, func.count())
        .where(ResearchProject.research_award_id.is_not(None))
        .group_by(ResearchProject.research_award_id)
    )).all())
    fund_counts = dict((r[0], int(r[1])) for r in (await session.execute(
        select(FundingArrangement.research_award_id, func.count())
        .where(FundingArrangement.research_award_id.is_not(None))
        .group_by(FundingArrangement.research_award_id)
    )).all())
    seen_award: set[uuid.UUID] = set()
    for grouping in (award_by_ref, award_by_title):
        for members in grouping.values():
            if len(members) < 2:
                continue
            ids = [m.id for m in members]
            if any(i in seen_award for i in ids):
                continue
            for i in ids:
                seen_award.add(i)
            out["awards"].append([
                {"id": str(m.id),
                 "label": f"{m.award_ref} — {m.title}",
                 "sub": (m.funder.name if getattr(m, "funder", None) else "no funder"),
                 "inUse": proj_counts.get(m.id, 0) + fund_counts.get(m.id, 0),
                 "createdAt": m.created_at.isoformat() if m.created_at else None}
                for m in members
            ])

    # ---------- Research projects (by research_topic) ------------------------
    projects = (await session.execute(
        select(ResearchProject).order_by(ResearchProject.created_at.asc())
    )).scalars().all()
    proj_groups: dict[str, list[ResearchProject]] = defaultdict(list)
    for p in projects:
        k = _norm(p.research_topic or "")
        if k:
            proj_groups[k].append(p)
    for members in proj_groups.values():
        if len(members) < 2:
            continue
        out["projects"].append([
            {"id": str(m.id),
             "label": m.research_topic or "(untitled project)",
             "sub": f"student {str(m.student_id)[:8]}…",
             "inUse": 1,          # a project always attaches to a student
             "createdAt": m.created_at.isoformat() if m.created_at else None}
            for m in members
        ])

    counts = {k: sum(len(g) for g in v) for k, v in out.items()}
    counts["groups"] = sum(len(v) for v in out.values())
    return {"groups": out, "counts": counts}


async def delete_if_unused(
    session: AsyncSession, *, kind: str, row_id: uuid.UUID
) -> dict:
    """Delete an opportunity, award, or project when nothing points at it. Refuses otherwise."""
    from app.core.errors import ConflictError, NotFoundError
    from app.modules.funding.models import FundingArrangement
    from app.modules.recruitment.models import Application, ResearchOpportunity
    from app.modules.research.models import ResearchAward
    from app.modules.student_record.models import ResearchProject

    if kind == "opportunity":
        row = await session.get(ResearchOpportunity, row_id)
        if row is None:
            raise NotFoundError("Opportunity not found")
        n = (await session.execute(
            select(func.count()).where(Application.research_opportunity_id == row_id)
        )).scalar_one()
        if n:
            raise ConflictError(
                f"Cannot delete — {n} application(s) reference this opportunity. "
                "Re-point or withdraw those first."
            )
    elif kind == "award":
        row = await session.get(ResearchAward, row_id)
        if row is None:
            raise NotFoundError("Award not found")
        p = (await session.execute(
            select(func.count()).where(ResearchProject.research_award_id == row_id)
        )).scalar_one()
        f = (await session.execute(
            select(func.count()).where(FundingArrangement.research_award_id == row_id)
        )).scalar_one()
        o = (await session.execute(
            select(func.count()).where(ResearchOpportunity.research_award_id == row_id)
        )).scalar_one()
        holders = []
        if p: holders.append(f"{p} project(s)")
        if f: holders.append(f"{f} funding arrangement(s)")
        if o: holders.append(f"{o} opportunity(s)")
        if holders:
            raise ConflictError("Cannot delete — still referenced by " + ", ".join(holders) + ".")
    elif kind == "project":
        row = await session.get(ResearchProject, row_id)
        if row is None:
            raise NotFoundError("Project not found")
        # A project's only "in use" signal is its student — deleting untethers that student.
    else:
        raise NotFoundError(f"Unknown kind: {kind}")

    await session.delete(row)
    await session.commit()
    return {"deleted": True}
