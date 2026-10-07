"""Read-only view of the effective HESA specifications (custom attribute governance, Phase 2).

A specification is named ``<PACK>:<YEAR>`` with the year's slash written as a hyphen so it fits a
path segment, e.g. ``HESA_STUDENT:2026-27``. What is returned is the *effective* pack — the
code baseline overlaid with any accepted advisory version (``spec_resolver``) — the same one the
mapping compile gate and the custom-attribute assessment read.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_any_permission
from app.core.errors import NotFoundError
from app.db.session import get_session

router = APIRouter(prefix="/hesa/specifications", tags=["exports"])

# Mapping staff read the spec; so do the people requesting or deciding custom attributes.
_READERS = ("reporting.read", "custom_attribute.request", "custom_attribute.approve")


def _key(spec: str) -> str:
    code, _, year = spec.partition(":")
    return f"{code}:{year.replace('-', '/')}"


def _spec_id(code: str, year: str) -> str:
    return f"{code}:{year.replace('/', '-')}"


def _field_out(f: dict) -> dict:
    return {
        "field": f.get("field", ""), "description": f.get("description", ""),
        "allowed": list(f.get("allowed") or []), "required": f.get("required", True),
        "source": f.get("source", "") or "", "keyedAt": f.get("keyed_at", ""),
    }


async def _pack(session: AsyncSession, spec: str) -> dict:
    from app.modules.exports.spec_resolver import resolve_pack

    pack = await resolve_pack(session, _key(spec))
    if pack is None:
        raise NotFoundError(f"No HESA specification '{spec}'")
    return pack


@router.get("", summary="Effective HESA specifications")
async def list_specifications(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_any_permission(*_READERS)),
) -> list[dict]:
    from app.modules.exports.spec_resolver import resolve_list_packs

    return [{**p, "id": _spec_id(p["code"], p["academicYear"])} for p in await resolve_list_packs(session)]


@router.get("/{spec}/fields", summary="Fields of one specification")
async def list_specification_fields(
    spec: str,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_any_permission(*_READERS)),
) -> dict:
    pack = await _pack(session, spec)
    return {
        "id": _spec_id(pack["code"], pack["academic_year"]), "code": pack["code"],
        "academicYear": pack["academic_year"], "version": pack["version"],
        "fields": [_field_out(f) for f in pack.get("fields", [])],
    }


@router.get("/{spec}/fields/{field}", summary="One field of a specification")
async def get_specification_field(
    spec: str,
    field: str,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_any_permission(*_READERS)),
) -> dict:
    pack = await _pack(session, spec)
    for f in pack.get("fields", []):
        if f.get("field", "").upper() == field.upper():
            return {**_field_out(f), "specification": _spec_id(pack["code"], pack["academic_year"]),
                    "version": pack["version"]}
    raise NotFoundError(f"'{field}' is not a field of {spec}")
