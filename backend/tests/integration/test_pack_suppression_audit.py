"""Pack-scope rule suppression audit trail.

Pack-scope suppression used to persist as a bare rule-key string; the sign-off card had
no by/when/reason to show, so a rule suppressed at pack level looked like it had just
vanished. Suppressions are now stored as {ruleKey, reason, at, byUserId, byUserName} —
same shape as profile-scope — while legacy string entries are still accepted on the
read/undo paths.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.exports.constants import SpecVersionStatus
from app.modules.exports.models import ReportProfile, StatutorySpecVersion
from app.modules.exports.statutory import StatutoryEngine


CODE = "HESA_STUDENT"
YEAR = "2026/27"
RULE_KEY = "order:COMDATE|ENDDATE"


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


async def _seed(s) -> ReportProfile:
    s.add(StatutorySpecVersion(
        pack_code=CODE, name="HESA Student", academic_year=YEAR, version=1,
        status=SpecVersionStatus.active,
        fields=[{"field": "COMDATE"}, {"field": "ENDDATE"}],
        rules=[{"kind": "order", "fields": ["COMDATE", "ENDDATE"],
                "message": "ENDDATE must be on or after COMDATE"}],
    ))
    profile = ReportProfile(code=CODE, name="HESA Student", academic_year=YEAR, version=1)
    s.add(profile)
    await s.commit()
    await s.refresh(profile)
    return profile


@pytest.mark.asyncio
async def test_pack_suppress_writes_audit_entry(session):
    """A new pack-scope suppression persists as a dict carrying who suppressed it and why —
    the sign-off card can then render an honest audit line, not just the rule key."""
    profile = await _seed(session)
    engine = StatutoryEngine(session)
    user_id = uuid.uuid4()

    await engine.suppress_rule(
        profile.id, rule_key=RULE_KEY, reason="Advisory 2026-08 relaxed this ordering rule.",
        scope="pack", user_id=user_id, user_name="Registry Owner",
    )

    version = (await session.execute(
        StatutorySpecVersion.__table__.select().where(
            StatutorySpecVersion.pack_code == CODE,
            StatutorySpecVersion.academic_year == YEAR,
        )
    )).mappings().first()
    entries = version["disabled_rule_keys"]
    assert len(entries) == 1
    assert isinstance(entries[0], dict)
    assert entries[0]["ruleKey"] == RULE_KEY
    assert entries[0]["reason"] == "Advisory 2026-08 relaxed this ordering rule."
    assert entries[0]["byUserName"] == "Registry Owner"
    assert entries[0]["at"], "timestamp is stamped at suppress time"


@pytest.mark.asyncio
async def test_pack_suppress_is_idempotent_on_same_key(session):
    """Clicking Suppress again for the same rule doesn't stack a second entry."""
    profile = await _seed(session)
    engine = StatutoryEngine(session)
    for _ in range(3):
        await engine.suppress_rule(
            profile.id, rule_key=RULE_KEY, reason="dup", scope="pack",
            user_id=uuid.uuid4(), user_name="R",
        )
    version = (await session.execute(
        StatutorySpecVersion.__table__.select()
    )).mappings().first()
    assert len(version["disabled_rule_keys"]) == 1


@pytest.mark.asyncio
async def test_collect_suppressions_promotes_legacy_string_entries(session):
    """Historic string entries (before the audit trail) surface with a 'legacy' marker so
    the audit UI doesn't crash and the operator can see the row exists."""
    profile = await _seed(session)
    version = (await session.execute(
        StatutorySpecVersion.__table__.select()
    )).mappings().first()
    # Simulate an old-shape entry directly in the DB.
    await session.execute(
        StatutorySpecVersion.__table__.update()
        .where(StatutorySpecVersion.id == version["id"])
        .values(disabled_rule_keys=[RULE_KEY])
    )
    await session.commit()

    engine = StatutoryEngine(session)
    profile = (await session.execute(
        ReportProfile.__table__.select().where(ReportProfile.id == profile.id)
    )).mappings().first()
    # _collect_suppressions takes the ORM row; refetch it.
    from sqlalchemy import select
    profile_orm = (await session.execute(
        select(ReportProfile).where(ReportProfile.id == profile["id"])
    )).scalar_one()

    entries = await engine._collect_suppressions(profile_orm)
    pack_entries = [e for e in entries if e.get("scope") == "pack"]
    assert len(pack_entries) == 1
    assert pack_entries[0]["ruleKey"] == RULE_KEY
    assert pack_entries[0]["byUserName"] == "legacy (before audit)"


@pytest.mark.asyncio
async def test_remove_suppression_handles_both_shapes(session):
    """Undo works whether the entry is a dict (new) or a bare string (legacy)."""
    profile = await _seed(session)
    engine = StatutoryEngine(session)

    # New shape.
    await engine.suppress_rule(
        profile.id, rule_key=RULE_KEY, reason="x", scope="pack",
        user_id=uuid.uuid4(), user_name="R",
    )
    await engine.remove_suppression(profile.id, rule_key=RULE_KEY, scope="pack")

    # Legacy string shape.
    from sqlalchemy import select
    version = (await session.execute(select(StatutorySpecVersion))).scalar_one()
    version.disabled_rule_keys = [RULE_KEY]
    await session.commit()
    await engine.remove_suppression(profile.id, rule_key=RULE_KEY, scope="pack")

    await session.refresh(version)
    assert version.disabled_rule_keys == []
