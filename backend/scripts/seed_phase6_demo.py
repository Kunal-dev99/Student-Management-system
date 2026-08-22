"""Demo data for the Phase 6 screens (research demand/awards + student lifecycle).

Idempotent: re-running it will not duplicate anything. Run from `backend/` against a seeded
database (PYTHONPATH so `app` resolves):

    PYTHONPATH=. python scripts/seed_phase6_demo.py
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

from sqlalchemy import select

from app.core.database import SessionFactory
from app.modules.funding.models import FundingSource
from app.modules.identity.models import User
from app.modules.person.models import Person
from app.modules.research.constants import DemandStatus
from app.modules.research.models import ResearchAward, ResearchDemand
from app.modules.research.repository import ResearchRepository
from app.modules.research.service import ResearchService
from app.modules.student_record.constants import LifecycleEventType, StudentStatus
from app.modules.student_record.lifecycle import LifecycleService
from app.modules.student_record.models import Student


async def main() -> None:
    async with SessionFactory() as s:
        svc = ResearchService(ResearchRepository(s))
        funder = (await s.execute(select(FundingSource).limit(1))).scalar_one_or_none()
        admin = (await s.execute(select(User).where(User.email == "admin@example.com"))).scalar_one_or_none()

        # 1) An award that arrived from the Research system — shows the read-only state.
        if not await svc.repo.get_award_by_ref("MRC/2026/0087"):
            await svc.upsert_from_research_system({
                "awardRef": "MRC/2026/0087",
                "title": "Longitudinal Health Outcomes in Ageing",
                "startDate": "2026-03-01", "endDate": "2031-02-28",
                "value": "3150000", "currency": "GBP", "externalRef": "MRC-SYS-88231",
            })
            print("  + synced award MRC/2026/0087 (read-only, from Research system)")

        # 2) A locally-recorded award (manual fallback).
        if not await svc.repo.get_award_by_ref("CHAR/2026/14"):
            await svc.create_award(
                award_ref="CHAR/2026/14", title="Charitable Trust Studentship Fund",
                funder_id=funder.id if funder else None,
                start_date=date(2026, 9, 1), end_date=date(2030, 8, 31),
                value=180000, currency="GBP",
            )
            print("  + local award CHAR/2026/14")

        # 3) Strategic demand with no award — proves demand need not be award-driven.
        existing = {d.title for d in await svc.repo.list_demands()}
        if "Departmental growth: data science" not in existing:
            d = await svc.create_demand(
                title="Departmental growth: data science", requested_places=2,
                justification="Strategic expansion agreed at faculty board; not award-funded.",
                target_start_date=date.today() + timedelta(days=120),
                raised_by_user_id=admin.id if admin else None,
            )
            await svc.transition_demand(d.id, DemandStatus.approved)
            print("  + strategic demand (no award), approved")

        # 4) Award-driven demand.
        award = await svc.repo.get_award_by_ref("MRC/2026/0087")
        if award and "Health outcomes PGR researcher" not in existing:
            await svc.create_demand(
                title="Health outcomes PGR researcher", research_award_id=award.id,
                requested_places=1,
                justification="Award milestone requires a PGR researcher from month 6.",
                target_start_date=date(2026, 10, 1),
                raised_by_user_id=admin.id if admin else None,
            )
            print("  + award-driven demand")

        # 5) A student with an approved extension, so the lifecycle panel has real history.
        row = (await s.execute(
            select(Student, Person).join(Person, Person.id == Student.person_id)
            .where(Student.status.in_([StudentStatus.registered, StudentStatus.active]))
        )).first()
        if row:
            student, person = row
            life = LifecycleService(s)
            already = [e for e in await life.events_for_student(student.id)
                       if e.event_type is LifecycleEventType.extension]
            if not already:
                if student.expected_end_date is None:
                    student.expected_end_date = (student.start_date or date.today()) + timedelta(days=1278)
                    await s.commit()
                ev = await life.request_event(
                    student.id, event_type=LifecycleEventType.extension,
                    reason="Fieldwork delayed by six weeks awaiting ethics approval.",
                    start_date=date.today(), extension_days=42,
                    requested_by_user_id=admin.id if admin else None,
                )
                out = await life.approve_event(
                    ev.id, approver_user_id=admin.id if admin else None,
                    note="Evidence reviewed; extension granted.",
                )
                print(f"  + extension approved for {person.given_name} {person.family_name}: "
                      f"{out['recalculation']['note']}")

    print("Phase 6 demo data ready.")


if __name__ == "__main__":
    asyncio.run(main())
