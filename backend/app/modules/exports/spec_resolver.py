"""Resolve the *effective* spec pack — code baseline overlaid with accepted advisories (ICR G5).

``specs.SPEC_PACKS`` is the shipped baseline (version 1). When the Registry accepts an advisory a
new ``StatutorySpecVersion`` row is written; from then on the effective pack for that return is the
latest ``active`` DB version, not the code constant. Every statutory consumer (``from_spec``,
validation ``rules_for``, the compile gate ``spec_for``, and the ``/specs`` picker) reads through
here, so an accepted advisory takes effect with no code change — and with the model off, nothing
about acceptance changes (it's pure DB state).

Overlay is *replace*, not merge: the accepted version stores the full resulting field/rule lists
(the parser already applied every directive), so the DB row is the whole pack for that key.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.exports.constants import SpecVersionStatus
from app.modules.exports.models import StatutorySpecVersion
from app.modules.exports.specs import (
    SpecPack,
    list_spec_packs,
    rules_for,
    spec_for,
    spec_pack,
)


def _pack_key(code: str, year: str) -> str:
    return f"{code}:{year}"


async def _active_for_code(
    session: AsyncSession, code: str, academic_year: str | None = None,
) -> StatutorySpecVersion | None:
    """The accepted spec version to use for a return code.

    With ``academic_year`` (the profile's own year), the *exact-year* active row is
    preferred — an advisory accepted against 2027/28 must never leak into a 2026/27
    profile's validation. Falls back to the latest year only when no row for the given
    year exists (baseline behaviour for a profile whose year has no ingested advisory).
    Callers without a year (bulk pickers, legacy paths) still get "latest wins".
    """
    q = (
        select(StatutorySpecVersion)
        .where(
            StatutorySpecVersion.pack_code == code,
            StatutorySpecVersion.status == SpecVersionStatus.active,
        )
        .order_by(
            StatutorySpecVersion.academic_year.desc(),
            StatutorySpecVersion.version.desc(),
        )
    )
    if academic_year is not None:
        exact = (
            await session.execute(
                q.where(StatutorySpecVersion.academic_year == academic_year)
            )
        ).scalars().first()
        if exact is not None:
            return exact
    rows = (await session.execute(q)).scalars().all()
    return rows[0] if rows else None


async def resolve_pack(session: AsyncSession, key: str) -> SpecPack | None:
    """The effective pack for a ``code:year`` key — the active DB version if present, else baseline."""
    baseline = spec_pack(key)
    code, _, year = key.partition(":")
    row = (
        await session.execute(
            select(StatutorySpecVersion)
            .where(
                StatutorySpecVersion.pack_code == code,
                StatutorySpecVersion.academic_year == year,
                StatutorySpecVersion.status == SpecVersionStatus.active,
            )
            .order_by(StatutorySpecVersion.version.desc())
        )
    ).scalars().first()
    if row is None:
        return baseline
    return {
        "code": row.pack_code,
        "name": row.name,
        "academic_year": row.academic_year,
        "version": row.version,
        "fields": list(row.fields or []),
        "rules": list(row.rules or []),
    }


async def resolve_fields(
    session: AsyncSession, code: str, academic_year: str | None = None,
) -> list[dict]:
    """Effective mandatory-field list for a return code (compile gate). Pass the profile's own
    ``academic_year`` so a same-year accepted advisory is used and cross-year advisories don't
    leak in."""
    row = await _active_for_code(session, code, academic_year)
    return list(row.fields or []) if row else list(spec_for(code))


async def resolve_rules(
    session: AsyncSession, code: str, academic_year: str | None = None,
) -> list[dict]:
    """Effective cross-field/format rules for a return code (validation) — filters out any rule
    keys the active pack version has disabled (pack-level suppression). ``academic_year`` scopes
    resolution to the profile's own year (see ``_active_for_code``)."""
    from app.modules.exports.statutory import _rule_key   # avoid import cycle
    row = await _active_for_code(session, code, academic_year)
    all_rules = list(row.rules or []) if row else list(rules_for(code))
    disabled = set(row.disabled_rule_keys or []) if row else set()
    return [r for r in all_rules if _rule_key(r) not in disabled]


async def active_version_for_code(
    session: AsyncSession, code: str, academic_year: str | None = None,
) -> StatutorySpecVersion | None:
    """Public accessor for the current active DB version — used by the pack-level suppression flow."""
    return await _active_for_code(session, code, academic_year)


async def resolve_list_packs(session: AsyncSession) -> list[dict]:
    """The pack picker — baseline packs with any accepted version overlaid (highest version wins)."""
    merged: dict[str, dict] = {}
    for p in list_spec_packs():
        merged[p["key"]] = p

    rows = (
        await session.execute(
            select(StatutorySpecVersion).where(
                StatutorySpecVersion.status == SpecVersionStatus.active
            )
        )
    ).scalars().all()
    for row in rows:
        key = _pack_key(row.pack_code, row.academic_year)
        existing = merged.get(key)
        if existing is None or row.version > existing.get("version", 0):
            merged[key] = {
                "key": key, "code": row.pack_code, "name": row.name,
                "academicYear": row.academic_year, "version": row.version,
                "fieldCount": len(row.fields or []),
            }
    # Stable order: by code then academic year.
    return sorted(merged.values(), key=lambda p: (p["code"], p.get("academicYear", "")))
