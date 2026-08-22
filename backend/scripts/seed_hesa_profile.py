"""Seed a HESA Student return profile (Phase 6.6).

A worked example of statutory reporting expressed as **configuration**: adding or amending a
return means editing these rows, not writing Python. Idempotent.

    PYTHONPATH=. python scripts/seed_hesa_profile.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import SessionFactory
from app.modules.exports.models import ReportProfile
from app.modules.exports.statutory import StatutoryEngine

CODE = "HESA_STUDENT"
YEAR = "2026/27"

# target field, source expression, transform, required, allowed values
FIELDS = [
    ("HUSID",            "student.ref",                    None,           True,  None),
    ("SURNAME",          "person.familyName",              "upper",        True,  None),
    ("FNAMES",           "person.givenName",               "upper",        True,  None),
    ("NATION",           "person.nationality",             "upper",        False, None),
    ("COURSEID",         "programme.code",                 None,           True,  None),
    ("MSTUFEE",          "funding.type",                   "lower",        False, None),
    ("STULOAD",          "student.mode",                   "lower",        True,
     ["full_time", "part_time"]),
    ("COMDATE",          "student.startDate",              "date_compact", True,  None),
    ("ENDDATE",          "student.expectedEndDate",        "date_compact", False, None),
    ("RSNROUTE",         "student.entryRoute",             "lower",        False,
     ["opportunity_led", "student_led"]),
    ("GRANT",            "funding.source",                 None,           False, None),
    ("AWARDREF",         "award.ref",                      None,           False, None),
]


async def main() -> None:
    async with SessionFactory() as s:
        engine = StatutoryEngine(s)
        existing = (await s.execute(
            select(ReportProfile).where(ReportProfile.code == CODE, ReportProfile.academic_year == YEAR)
        )).scalar_one_or_none()
        if existing:
            print(f"HESA profile {YEAR} already present ({existing.id}).")
            return

        profile = await engine.create_profile(
            code=CODE, name="HESA Student Return", academic_year=YEAR,
            description="Worked example: the statutory return expressed entirely as configuration.",
        )
        for position, (target, source, transform, required, allowed) in enumerate(FIELDS, start=1):
            await engine.add_field(
                profile.id, target_field=target, source_expression=source, position=position,
                transform=transform, required=required, allowed_values=allowed,
            )
        print(f"Seeded {CODE} {YEAR} with {len(FIELDS)} mapped fields (profile {profile.id}).")

        result = await engine.generate(profile.id)
        v = result["validation"]
        print(f"Dry run: {result['rowCount']} rows, {v['errors']} validation error(s).")
        for issue in v["issues"][:5]:
            print(f"  - {issue['studentRef']}: {issue['message']}")


if __name__ == "__main__":
    asyncio.run(main())
