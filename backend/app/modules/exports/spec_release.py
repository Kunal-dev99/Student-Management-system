"""Regulatory updates under subscription (Demo 2 item 1.21): releasing a HESA specification centrally.

Specification versions are platform-wide (one ``statutory_spec_version`` row per pack, year and
version), and only the platform team can change them. Each institution's return profiles read
the active version for their pack and year, so a release reaches every subscriber at once.

This module adds what a release needs around that:

* ``list_versions`` - every version of a pack and year, the active one marked;
* ``restore`` - make an earlier version active again (rolling back a bad release);
* ``impact`` - for one institution, which of its returns use the pack and year, and what each
  must still do before it can be signed off (missing and unmapped required fields), using the
  same check as the sign-off screen. ``scripts/spec_release.py`` runs it for every institution.

See docs/statutory/REGULATORY_RELEASE_PROCESS.md for the procedure.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.exports.constants import SpecVersionStatus
from app.modules.exports.models import ReportProfile, StatutorySpecVersion


def version_out(v: StatutorySpecVersion) -> dict:
    return {
        "id": str(v.id), "packCode": v.pack_code, "academicYear": v.academic_year, "version": v.version,
        "name": v.name, "status": v.status.value if hasattr(v.status, "value") else v.status,
        "fieldCount": len(v.fields or []), "ruleCount": len(v.rules or []),
        "fromAdvisory": str(v.source_advisory_id) if v.source_advisory_id else None,
        "createdAt": v.created_at.isoformat() if getattr(v, "created_at", None) else None,
    }


async def list_versions(session: AsyncSession, pack_code: str, academic_year: str) -> list[StatutorySpecVersion]:
    return list((await session.execute(
        select(StatutorySpecVersion).where(StatutorySpecVersion.pack_code == pack_code,
                                           StatutorySpecVersion.academic_year == academic_year)
        .order_by(StatutorySpecVersion.version.desc()))).scalars())


async def restore(session: AsyncSession, version_id: uuid.UUID, *, user_id: uuid.UUID | None) -> StatutorySpecVersion:
    """Make ``version_id`` the active version of its pack and year; the others become superseded.
    Nothing is deleted, so restoring the later version again undoes the rollback."""
    target = await session.get(StatutorySpecVersion, version_id)
    if target is None:
        raise NotFoundError("Specification version not found")
    for v in await list_versions(session, target.pack_code, target.academic_year):
        v.status = SpecVersionStatus.active if v.id == target.id else SpecVersionStatus.superseded
    target.accepted_by = user_id
    await session.commit()
    return target


async def impact(session: AsyncSession, pack_code: str, academic_year: str) -> list[dict]:
    """The acting institution's return profiles on this pack and year, with what each still needs.
    The session must be acting as the institution (``tenant_scope``)."""
    from app.modules.exports.statutory import StatutoryEngine

    engine = StatutoryEngine(session)
    profiles = (await session.execute(select(ReportProfile).where(
        ReportProfile.code == pack_code, ReportProfile.academic_year == academic_year,
        ReportProfile.is_active.is_(True)).order_by(ReportProfile.name))).scalars().all()
    out = []
    for p in profiles:
        gap = await engine.compile(p.id)
        out.append({
            "profileId": str(p.id), "profile": p.name, "signedOff": p.signed_off_at is not None,
            "missing": [m["field"] for m in gap["missing"]],
            "unmappedRequired": gap["unmappedRequired"],
            "ready": gap["signOffReady"],
        })
    return out
