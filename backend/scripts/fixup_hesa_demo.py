"""Make the HESA demo validate green.

The 2026/27 HESA Student profile in the demo DB was assembled through hand-edits
that no longer match the spec pack (SEXID mapped to person.nationality, MODE's
coding frame narrowed to ["99"], and so on). At the same time the bulk cohort
was seeded without the person-level fields the spec needs — date of birth,
nationality, and an application whose route drives ENTRYROUTE.

This script:

  * backfills every Person without a date of birth / nationality with a
    deterministic value seeded from their id (so re-runs are idempotent);
  * creates one Application per Student that doesn't have one, so the return's
    ENTRYROUTE field surfaces;
  * makes sure every Student has a ResearchProject (topic populates THESIS);
  * resets the "HESA_STUDENT / 2026/27" profile to a clean, spec-aligned set of
    field mappings with defensible defaults for the codes we cannot yet source.

Idempotent. Run:
    python -m scripts.fixup_hesa_demo
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import SessionFactory
from app.db import registry as _registry  # noqa: F401 — force full mapper registration
from app.modules.exports.models import ReportProfile, StatutorySpecVersion
from app.modules.exports.specs import HESA_STUDENT_2026
from app.modules.exports.statutory import StatutoryEngine
from app.modules.person.models import Person
from app.modules.recruitment.constants import ApplicationRoute, CandidateStage
from app.modules.recruitment.models import Application
from app.modules.student_record.models import ResearchProject, Student

CODE = "HESA_STUDENT"
YEAR = "2026/27"

# Nationality pool (roughly matches ICR's real UK-heavy PGR mix).
NATIONALITIES = ["GB", "GB", "GB", "GB", "GB", "GB", "IE", "IN", "CN", "NG", "US", "DE", "FR", "IT", "PL"]


def _stable_choice(seed: str, pool: list) -> object:
    """Deterministic pick from `pool` seeded from a stable string (e.g. a UUID).
    Re-running the script gives every person the same value it got last time."""
    n = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16)
    return pool[n % len(pool)]


def _stable_dob(seed: str, today: date) -> date:
    """Deterministic DOB between 22 and 40 years before today."""
    n = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16)
    age_years = 22 + (n % 18)                       # 22..39
    day_offset = (n // 100) % 365                   # spread within the year
    return today.replace(year=today.year - age_years) - timedelta(days=day_offset)


async def backfill_persons(session) -> int:
    """Fill missing dateOfBirth / nationality on every Person."""
    today = date.today()
    persons = (await session.execute(select(Person))).scalars().all()
    touched = 0
    for p in persons:
        changed = False
        seed = str(p.id)
        if getattr(p, "date_of_birth", None) is None:
            p.date_of_birth = _stable_dob(seed, today)
            changed = True
        if not getattr(p, "nationality", None):
            p.nationality = _stable_choice(seed, NATIONALITIES)
            changed = True
        if changed:
            touched += 1
    return touched


async def ensure_applications(session) -> int:
    """One Application per Student who doesn't already have one — so student.entryRoute
    resolves to a real value (opportunity_led / student_led → OPPORTUNITY / PROPOSAL)."""
    students = (await session.execute(select(Student))).scalars().all()
    existing_person_ids = {
        a.person_id for a in (await session.execute(select(Application))).scalars().all()
    }
    created = 0
    for s in students:
        if s.person_id in existing_person_ids:
            continue
        # Deterministic mix — roughly 70% opportunity-led (matches the ICR model).
        route = _stable_choice(str(s.id), [
            ApplicationRoute.opportunity_led, ApplicationRoute.opportunity_led,
            ApplicationRoute.opportunity_led, ApplicationRoute.student_led,
        ])
        submitted = datetime.combine(
            s.start_date - timedelta(days=180) if s.start_date else date.today(),
            datetime.min.time(), tzinfo=timezone.utc,
        )
        session.add(Application(
            person_id=s.person_id, route=route,
            current_stage=CandidateStage.converted,
            submitted_at=submitted,
        ))
        existing_person_ids.add(s.person_id)
        created += 1
    return created


async def backfill_expected_end(session) -> int:
    """Every Student needs expected_end_date — ENDDATE is required by the HESA spec. Compute
    from the programme's typical duration where the field is null."""
    students = (await session.execute(
        select(Student).where(Student.expected_end_date.is_(None))
    )).scalars().all()
    touched = 0
    for st in students:
        if st.start_date is None:
            continue
        # 1460 days for a full PhD, 1095 for an MDRes-style shorter programme; if we can't
        # tell, use PhD as the safer default (over- rather than under-estimate).
        limit_days = 1095 if "MDRES" in (getattr(st, "programme_code", "") or "") else 1460
        st.expected_end_date = st.start_date + timedelta(days=limit_days)
        if st.original_expected_end_date is None:
            st.original_expected_end_date = st.expected_end_date
        touched += 1
    return touched


async def ensure_research_projects(session) -> int:
    """Every Student should have a ResearchProject with a non-empty topic (feeds THESIS).
    Creates one where missing; backfills the topic on existing projects that were persisted
    without one."""
    students = (await session.execute(select(Student))).scalars().all()
    projects = (await session.execute(select(ResearchProject))).scalars().unique().all()
    by_student = {p.student_id: p for p in projects}
    fallback_topics = [
        "Computational modelling of tumour heterogeneity",
        "Immune signatures in early-stage disease",
        "Radiotherapy response biomarkers",
        "Single-cell profiling of the tumour microenvironment",
        "Targeted therapy resistance mechanisms",
    ]
    created = 0
    for s in students:
        topic = _stable_choice(str(s.id), fallback_topics)
        existing = by_student.get(s.id)
        if existing is None:
            session.add(ResearchProject(
                student_id=s.id, research_topic=topic,
                start_date=s.start_date or date.today(),
            ))
            created += 1
        elif not (existing.research_topic or "").strip():
            existing.research_topic = topic
            created += 1
    return created


async def reset_profile(session) -> str:
    """Delete the existing HESA_STUDENT/2026/27 profile (fields cascade) and rebuild it
    from the spec pack, giving each field a defensible default where the spec doesn't
    yet have a source. That means a fresh Validate should have zero errors."""
    engine = StatutoryEngine(session)

    # Codes we can't yet source from the domain model — a spec fallback keeps the return
    # signable. Each value is either the sole allowed code, the "not known" code, or the
    # HESA-blessed placeholder.
    field_defaults = {
        "SEXID": "13",       # "not specified"
        "ETHNIC": "98",      # "information refused"
        "DISABLE": "00",     # "no known disability"
        "COURSETYP": "A",
        "STUDYLEVEL": "D00", # doctorate — every PGR
        "FEESTAT": "9",
        "MSTUFEE": "99",
        "FUNDCODE": "9",
        "DOMICILE": "GB",
        "TERMTIME": "9",
        "SUPERVISED": "Y",   # PGR
    }

    existing = (await session.execute(
        select(ReportProfile).where(ReportProfile.code == CODE, ReportProfile.academic_year == YEAR)
    )).scalar_one_or_none()
    if existing is not None:
        await session.delete(existing)
        await session.flush()

    profile = await engine.create_profile(
        code=CODE, name="HESA Student Return", academic_year=YEAR,
        description="Worked example: the statutory return expressed entirely as configuration.",
    )
    for i, spec in enumerate(HESA_STUDENT_2026, start=1):
        await engine.add_field(
            profile.id,
            target_field=spec["field"],
            source_expression=spec.get("source") or "",
            position=i,
            transform=spec.get("transform"),
            required=spec.get("required", True),
            allowed_values=spec.get("allowed"),
            default_value=spec.get("default") or field_defaults.get(spec["field"]),
        )
    return str(profile.id)


async def cleanse_spec_versions(session) -> int:
    """Some ingested advisory versions carry an "order" rule with the fields reversed
    (["ENDDATE","COMDATE"] instead of ["COMDATE","ENDDATE"]). Because resolve_rules picks
    the LATEST year's pack for a return code, that bogus rule fires against every profile
    of the same code — every valid record (ENDDATE > COMDATE) is misreported as an
    ordering violation. Drop the reversed duplicate wherever it appears."""
    rows = (await session.execute(select(StatutorySpecVersion))).scalars().all()
    fixed = 0
    for row in rows:
        rules = list(row.rules or [])
        keep: list[dict] = []
        for r in rules:
            if r.get("kind") == "order" and r.get("fields") == ["ENDDATE", "COMDATE"]:
                continue  # reversed duplicate — drop
            keep.append(r)
        if len(keep) != len(rules):
            row.rules = keep
            fixed += 1
    return fixed


async def main() -> None:
    async with SessionFactory() as s:
        persons_touched = await backfill_persons(s)
        apps_created = await ensure_applications(s)
        projs_created = await ensure_research_projects(s)
        ends_backfilled = await backfill_expected_end(s)
        rules_fixed = await cleanse_spec_versions(s)
        await s.flush()
        new_profile_id = await reset_profile(s)
        await s.commit()

        # Dry-run validation on the freshly-reset profile so operators see the outcome.
        engine = StatutoryEngine(s)
        result = await engine.generate(new_profile_id)
        v = result["validation"]
        print(f"Backfilled {persons_touched} persons, {apps_created} applications, {projs_created} projects, {ends_backfilled} expected-end dates; cleansed {rules_fixed} spec versions.")
        print(f"Rebuilt profile {CODE}/{YEAR} — {result['rowCount']} rows, {v['errors']} errors, {v.get('warnings', 0)} warnings.")
        for issue in v["issues"][:5]:
            print(f"  - {issue['studentRef']}: {issue['message']}")


if __name__ == "__main__":
    asyncio.run(main())
