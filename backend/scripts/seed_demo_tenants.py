"""Seed a few demo tenants (besides the default/ICR deployment) to show isolation.

For each tenant it creates the tenant row, then — acting AS that tenant (tenant context set,
so RLS and insert-stamping apply) — a taught programme and three enrolled students through
the normal service layer. Idempotent on the tenant subdomain.

    python -m scripts.seed_demo_tenants
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date

from sqlalchemy import select, text

from app.core.database import SessionFactory
from app.core.tenant_context import set_current_tenant
from app.modules.person.schemas import PersonCreate
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.repository import StudentRepository
from app.modules.student_record.schemas import ProgrammeCreate
from app.modules.student_record.service import StudentService
from app.modules.tenant.models import Tenant

TENANTS = [
    ("Oxbridge University", "oxbridge", "MSC-OXB", "MSc Data Science",
     ["Amara Osei", "Liang Wei", "Noah Fisher"]),
    ("Metro College", "metro", "MSC-MET", "MSc Public Health",
     ["Sara Khan", "Diego Mata", "Ivy Chen"]),
    ("Riverside Institute", "riverside", "MSC-RIV", "MSc Marine Biology",
     ["Owen Pryce", "Lucia Romano", "Kwame Mensah"]),
]


async def main() -> None:
    for name, sub, code, prog_name, students in TENANTS:
        async with SessionFactory() as s:
            existing = (await s.execute(select(Tenant).where(Tenant.subdomain == sub))).scalar_one_or_none()
            if existing:
                print(f"  {sub}: already exists — skipping")
                continue
            tenant = Tenant(name=name, subdomain=sub)
            from datetime import datetime, timezone
            tenant.activated_at = datetime.now(timezone.utc)
            s.add(tenant)
            await s.commit()
            await s.refresh(tenant)

            # Act as this tenant for everything below (ORM stamping + RLS WITH CHECK).
            set_current_tenant(tenant.id)
            # (T1: every transaction publishes the context tenant to Postgres automatically.)

            svc = StudentService(StudentRepository(s))
            prog = await svc.create_programme(ProgrammeCreate(
                name=prog_name, code=code, programmeType="taught", durationMonths=12,
            ))
            for i, full in enumerate(students, 1):
                given, family = full.split(" ", 1)
                await svc.enrol(
                    person_id=None,
                    person_data=PersonCreate(
                        given_name=given, family_name=family,
                        email=f"{given.lower()}.{family.lower()}@{sub}.demo",
                    ),
                    programme_id=prog.id,
                    start_date=date(2026, 9, 28),
                    study_mode=StudyMode.full_time,
                    status=StudentStatus.registered,
                    student_ref=f"{sub.upper()}-{i:03d}",
                )
            print(f"  {sub}: tenant + programme {code} + {len(students)} students")

            set_current_tenant(None)


if __name__ == "__main__":
    asyncio.run(main())
