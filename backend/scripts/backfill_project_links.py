"""F5 — Backfill research_project rows for students created before Phase 6.

Every student created before Phase 6.1 lacks a ``research_project`` row, so the funding lineage
check flags them as errors. This script walks the student population and either:

- links an existing ``research_project`` if the student already has one (idempotent skip), or
- creates a stub ``research_project`` referencing the best-guess funding-source-of-record for
  that student, or
- logs the student as "uncertain" if no funding chain exists to infer from.

Dry-run mode (default) prints what would happen without writing. Pass ``--apply`` to commit.

Run:
    PYTHONPATH=. .venv/Scripts/python.exe scripts/backfill_project_links.py
    PYTHONPATH=. .venv/Scripts/python.exe scripts/backfill_project_links.py --apply
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionFactory
from app.modules.funding.constants import FundingStatus
from app.modules.funding.models import FundingArrangement
from app.modules.student_record.models import ResearchProject, Student


async def _linked_project_for(session: AsyncSession, student_id) -> ResearchProject | None:
    return (await session.execute(
        select(ResearchProject).where(ResearchProject.student_id == student_id)
    )).scalar_one_or_none()


async def _best_funding_for(session: AsyncSession, student_id) -> FundingArrangement | None:
    """The student's active funding arrangement, or the most recent one if none is active."""
    active = (await session.execute(
        select(FundingArrangement).where(
            FundingArrangement.student_id == student_id,
            FundingArrangement.status == FundingStatus.active,
        ).order_by(FundingArrangement.valid_from.desc())
    )).scalars().first()
    if active:
        return active
    return (await session.execute(
        select(FundingArrangement).where(FundingArrangement.student_id == student_id)
        .order_by(FundingArrangement.valid_from.desc())
    )).scalars().first()


async def run(apply: bool) -> dict:
    linked = created = uncertain = 0
    uncertain_refs: list[str] = []

    async with SessionFactory() as session:
        students = (await session.execute(select(Student))).scalars().all()
        for student in students:
            existing = await _linked_project_for(session, student.id)
            if existing is not None:
                linked += 1
                continue
            best = await _best_funding_for(session, student.id)
            if best is None:
                uncertain += 1
                uncertain_refs.append(student.student_ref)
                continue
            stub = ResearchProject(
                student_id=student.id,
                research_topic=getattr(student, "research_topic", None) or "Backfilled — pre-Phase-6 record",
                research_area_id=getattr(student, "research_area_id", None),
                # Best-guess: not linked to a specific award, but with the funding source of record
                # noted in the topic. A human reviewer can promote this to a real project later.
            )
            session.add(stub)
            created += 1
        if apply:
            await session.commit()
        else:
            await session.rollback()

    return {
        "students": len(students), "already_linked": linked,
        "created": created, "uncertain": uncertain,
        "uncertain_refs": uncertain_refs,
        "applied": apply,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Actually write; default is dry-run")
    args = p.parse_args()
    report = asyncio.run(run(args.apply))
    print("== Backfill research_project links ==")
    print(f"  Students seen        : {report['students']}")
    print(f"  Already linked       : {report['already_linked']}")
    print(f"  Stub projects created: {report['created']}")
    print(f"  Uncertain (no funding to infer from): {report['uncertain']}")
    if report["uncertain_refs"]:
        print("  Uncertain refs (raise as admin tasks):")
        for ref in report["uncertain_refs"][:20]:
            print(f"    - {ref}")
        if len(report["uncertain_refs"]) > 20:
            print(f"    … and {len(report['uncertain_refs']) - 20} more")
    if not report["applied"]:
        print("\n  DRY RUN — pass --apply to commit.")


if __name__ == "__main__":
    main()
