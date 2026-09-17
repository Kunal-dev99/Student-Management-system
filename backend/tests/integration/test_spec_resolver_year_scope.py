"""spec_resolver: rule/field resolution must scope to the profile's own academic year.

Regression for the reversed-order-rule leak: an advisory accepted against 2027/28 was
firing against every 2026/27 profile because `_active_for_code` picked the latest-year
pack for a code, ignoring which year the caller actually cared about. Threading
academic_year through resolve_fields/resolve_rules/active_version_for_code fixes it.
This test pins that: a rule that only exists on a NEWER year's pack must not appear
when resolving for an OLDER year that has its own accepted pack.
"""
from __future__ import annotations

import pytest_asyncio
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.exports.constants import SpecVersionStatus
from app.modules.exports.models import StatutorySpecVersion
from app.modules.exports.spec_resolver import (
    _active_for_code,
    resolve_fields,
    resolve_rules,
)


CODE = "HESA_STUDENT"

OLDER_RULE = {"kind": "order", "fields": ["COMDATE", "ENDDATE"],
              "message": "ENDDATE must be on or after COMDATE"}
POISONED_RULE = {"kind": "order", "fields": ["ENDDATE", "COMDATE"],
                 "message": "leaked from a newer year — must not fire on the older profile",
                 "severity": "error"}


@pytest_asyncio.fixture
async def session():
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        yield s
    await eng.dispose()


async def _seed_two_years(s):
    s.add(StatutorySpecVersion(
        pack_code=CODE, name="HESA Student", academic_year="2026/27", version=1,
        status=SpecVersionStatus.active,
        fields=[{"field": "COMDATE"}, {"field": "ENDDATE"}],
        rules=[OLDER_RULE],
    ))
    s.add(StatutorySpecVersion(
        pack_code=CODE, name="HESA Student", academic_year="2028/29", version=2,
        status=SpecVersionStatus.active,
        fields=[{"field": "COMDATE"}, {"field": "ENDDATE"}, {"field": "NEWCODE"}],
        rules=[OLDER_RULE, POISONED_RULE],
    ))
    await s.commit()


@pytest.mark.asyncio
async def test_resolve_rules_scopes_to_profile_year(session):
    """The 2026/27 profile must see only its own year's rules; the poisoned rule from
    2028/29 must not appear even though 2028/29 is the latest year on file."""
    await _seed_two_years(session)

    rules = await resolve_rules(session, CODE, "2026/27")
    fields_lists = [r["fields"] for r in rules]

    assert ["COMDATE", "ENDDATE"] in fields_lists, "the older year's own rule should still resolve"
    assert ["ENDDATE", "COMDATE"] not in fields_lists, (
        "poisoned rule from a newer year leaked into the older profile's resolution"
    )


@pytest.mark.asyncio
async def test_resolve_rules_still_returns_newer_year_when_asked(session):
    """Same input, different profile year — 2028/29 gets its own (larger) rule set."""
    await _seed_two_years(session)

    rules = await resolve_rules(session, CODE, "2028/29")
    fields_lists = [r["fields"] for r in rules]

    assert ["COMDATE", "ENDDATE"] in fields_lists
    assert ["ENDDATE", "COMDATE"] in fields_lists


@pytest.mark.asyncio
async def test_resolve_falls_back_to_latest_when_year_missing(session):
    """A profile in a year with no ingested pack falls back to whichever year IS active —
    baseline behaviour we still rely on for years the Registry hasn't touched yet."""
    await _seed_two_years(session)

    row = await _active_for_code(session, CODE, "2029/30")
    assert row is not None
    assert row.academic_year == "2028/29", "falls back to latest active year when exact match missing"


@pytest.mark.asyncio
async def test_resolve_fields_scopes_to_year(session):
    """Fields resolution scopes too — otherwise the compile gate would demand a NEWCODE
    field from a profile whose year never included it."""
    await _seed_two_years(session)

    older_fields = {f["field"] for f in await resolve_fields(session, CODE, "2026/27")}
    newer_fields = {f["field"] for f in await resolve_fields(session, CODE, "2028/29")}

    assert "NEWCODE" in newer_fields
    assert "NEWCODE" not in older_fields, "newer year's field leaked into older profile's spec"


@pytest.mark.asyncio
async def test_no_year_argument_preserves_legacy_latest_wins(session):
    """Callers without a year (bulk pickers, legacy paths) still get latest-wins."""
    await _seed_two_years(session)

    row = await _active_for_code(session, CODE)
    assert row is not None
    assert row.academic_year == "2028/29"
