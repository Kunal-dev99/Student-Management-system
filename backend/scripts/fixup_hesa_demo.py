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


SYNTHETIC_APPLICATION_MARKER = "__fixup_hesa_demo:entryroute_only__"


async def ensure_applications(session) -> int:
    """One Application per Student who doesn't already have one — so student.entryRoute
    resolves to a real value (opportunity_led / student_led → OPPORTUNITY / PROPOSAL).

    IMPORTANT: these Applications are SYNTHETIC — they exist purely so the HESA return can
    populate ENTRYROUTE. A directly-enrolled student (ICR G2) never went through the funnel,
    so we deliberately do NOT create ``CandidateStageHistory`` rows for them. That's how the
    journey tracker (via ``person_has_application``) tells a real applicant from a synthetic
    fixup one. The ``proposal_document_ref`` also carries an explicit marker so any future
    cleanup can identify and prune these rows if the domain grows a proper direct-enrol flag.
    """
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
            proposal_document_ref=SYNTHETIC_APPLICATION_MARKER,
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


# Which per-field defaults are correct-by-model vs stand-in-for-missing-data. The demo
# validates green with either, but honesty matters: a "not known" code isn't a real answer
# for a real return — the operator running fixup needs to see which fields the return would
# ship as placeholders. The two categories are:
#
#   CORRECT_BY_MODEL  — the value is a fact about the ICR PGR population, not a placeholder.
#                       E.g. STUDYLEVEL is D00 because every ICR student in the return is a
#                       doctoral candidate; SUPERVISED is Y because every PGR has a supervisor.
#
#   NOT_CAPTURED_YET  — the domain model doesn't collect this field. The value is the HESA
#                       "not known / refused / unspecified" code — legally shippable, but the
#                       operator should know real capture is still outstanding.
CORRECT_BY_MODEL: dict[str, str] = {
    "STUDYLEVEL": "D00",   # every student in this return is a doctoral candidate
    "SUPERVISED": "Y",     # every PGR is supervised
}
NOT_CAPTURED_YET: dict[str, str] = {
    "SEXID":     "13",     # "not specified"
    "ETHNIC":    "98",     # "information refused"
    "DISABLE":   "00",     # "no known disability"
    "COURSETYP": "A",      # placeholder — full-time academic year
    "FEESTAT":   "9",      # "not known"
    "MSTUFEE":   "99",     # "not classified elsewhere"
    "FUNDCODE":  "9",      # "other"
    "DOMICILE":  "GB",     # placeholder — real domicile capture pending
    "TERMTIME":  "9",      # "not known"
}


async def reset_profile(session) -> tuple[str, list[str]]:
    """Delete the existing HESA_STUDENT/2026/27 profile (fields cascade) and rebuild it
    from the spec pack, giving each field either a correct-by-model or a spec-fallback
    default so a fresh Validate is green. Returns (new_profile_id, warnings).

    Suppressions the operator had set on the old profile are carried across — losing them
    silently on a fixup rerun would silently un-mute rules the return relied on."""
    engine = StatutoryEngine(session)

    existing = (await session.execute(
        select(ReportProfile).where(ReportProfile.code == CODE, ReportProfile.academic_year == YEAR)
    )).scalar_one_or_none()
    carried_suppressions: list = []
    if existing is not None:
        carried_suppressions = list(existing.muted_rule_keys or [])
        await session.delete(existing)
        await session.flush()

    profile = await engine.create_profile(
        code=CODE, name="HESA Student Return", academic_year=YEAR,
        description="Worked example: the statutory return expressed entirely as configuration.",
    )
    for i, spec in enumerate(HESA_STUDENT_2026, start=1):
        default = (
            spec.get("default")
            or CORRECT_BY_MODEL.get(spec["field"])
            or NOT_CAPTURED_YET.get(spec["field"])
        )
        await engine.add_field(
            profile.id,
            target_field=spec["field"],
            source_expression=spec.get("source") or "",
            position=i,
            transform=spec.get("transform"),
            required=spec.get("required", True),
            allowed_values=spec.get("allowed"),
            default_value=default,
        )

    # Carry profile-scope suppressions across the rebuild.
    if carried_suppressions:
        refreshed = (await session.execute(
            select(ReportProfile).where(ReportProfile.id == profile.id)
        )).scalar_one()
        refreshed.muted_rule_keys = carried_suppressions

    warnings = [
        f"{field} defaulted to {value!r} — {NOT_CAPTURED_YET[field]!r} is a HESA "
        f"'not known' placeholder; wire the real domain source before a live submission."
        for field, value in NOT_CAPTURED_YET.items()
    ]
    if carried_suppressions:
        warnings.append(f"Carried {len(carried_suppressions)} profile-scope suppression(s) across the rebuild.")
    return str(profile.id), warnings


async def cleanse_spec_versions(session) -> int:
    """Historical: strips a reversed-order rule (["ENDDATE","COMDATE"]) that had leaked
    into a newer year's pack version. The underlying cross-year leak is now closed at the
    source — resolve_fields/resolve_rules scope to the profile's own academic year — so
    this scrub is only useful for tidying already-polluted DBs. Safe to keep as a no-op
    on clean data."""
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
        new_profile_id, reset_warnings = await reset_profile(s)
        await s.commit()

        # Dry-run validation on the freshly-reset profile so operators see the outcome.
        engine = StatutoryEngine(s)
        result = await engine.generate(new_profile_id)
        v = result["validation"]
        print(f"Backfilled {persons_touched} persons, {apps_created} applications, {projs_created} projects, {ends_backfilled} expected-end dates; cleansed {rules_fixed} spec versions.")
        print(f"Rebuilt profile {CODE}/{YEAR} — {result['rowCount']} rows, {v['errors']} errors, {v.get('warnings', 0)} warnings.")
        for issue in v["issues"][:5]:
            print(f"  - {issue['studentRef']}: {issue['message']}")
        if reset_warnings:
            print("")
            print("Advisories (integrity — not blockers):")
            for w in reset_warnings:
                print(f"  ! {w}")


if __name__ == "__main__":
    asyncio.run(main())
