"""Effective dating, Phase 1 — PostgreSQL-only guarantees for student status history.

Runs against the configured database when it is PostgreSQL and migrated to ``ed1_status_history``
or later; skipped otherwise (the SQLite suite covers the service logic). Everything runs inside a
transaction that is rolled back, so the database is left untouched.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


@pytest_asyncio.fixture
async def engine():
    # A fresh engine per test: pooled asyncpg connections are bound to one event loop.
    url = get_settings().database_url
    if not url.startswith("postgresql"):
        pytest.skip("PostgreSQL-only guarantees; skipped on other dialects")
    # These are whole-database consistency checks, so they read every tenant: since T1 that
    # needs the owner's explicit bypass, or fail-closed RLS shows them no rows at all.
    eng = create_async_engine(url, poolclass=NullPool,
                              connect_args={"server_settings": {"app.bypass_tenant": "on"}})
    try:
        async with eng.connect() as conn:
            exists = await conn.scalar(text("SELECT to_regclass('public.student_status_history')"))
    except Exception:
        await eng.dispose()
        pytest.skip("PostgreSQL not reachable")
    if exists is None:
        await eng.dispose()
        pytest.skip("Database not migrated to ed1_status_history yet")
    yield eng
    await eng.dispose()


async def test_table_is_tenant_isolated(engine):
    async with engine.connect() as conn:
        rls = (await conn.execute(text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'student_status_history'"
        ))).one()
        assert tuple(rls) == (True, True)
        policies = await conn.scalar(text(
            "SELECT count(*) FROM pg_policies WHERE tablename = 'student_status_history' "
            "AND policyname = 'tenant_isolation'"
        ))
        assert policies == 1


async def test_enum_values_and_permission_exist(engine):
    async with engine.connect() as conn:
        statuses = set(await conn.scalars(text("SELECT unnest(enum_range(NULL::student_status))::text")))
        assert "writing_up" in statuses
        events = set(await conn.scalars(text("SELECT unnest(enum_range(NULL::lifecycle_event_type))::text")))
        assert {"writing_up", "withdrawal", "termination"} <= events
        granted = set(await conn.scalars(text(
            "SELECT r.name FROM role r JOIN role_permission rp ON rp.role_id = r.id "
            "JOIN permission p ON p.id = rp.permission_id WHERE p.code = 'student.history.correct'"
        )))
        assert "Institution Administrator" in granted


async def test_every_student_has_history_matching_today(engine):
    async with engine.connect() as conn:
        mismatched = await conn.scalar(text(
            "SELECT count(*) FROM student s "
            "JOIN student_status_history h ON h.student_id = s.id AND h.superseded_by IS NULL "
            " AND h.valid_from <= current_date AND (h.valid_to IS NULL OR h.valid_to > current_date) "
            "WHERE h.status <> s.status"
        ))
        assert mismatched == 0
        without = await conn.scalar(text(
            "SELECT count(*) FROM student s WHERE NOT EXISTS "
            "(SELECT 1 FROM student_status_history h WHERE h.student_id = s.id)"
        ))
        assert without == 0


async def test_overlapping_live_periods_are_rejected(engine):
    async with engine.connect() as conn:
        has_constraint = await conn.scalar(text(
            "SELECT count(*) FROM pg_constraint WHERE conname = 'ex_student_status_history_no_overlap'"
        ))
        if not has_constraint:
            pytest.skip("No-overlap constraint not installed (btree_gist unavailable when migrating)")
        sid = await conn.scalar(text("SELECT id FROM student LIMIT 1"))
        if sid is None:
            pytest.skip("No students to test against")
        await conn.rollback()   # end the auto-begun read transaction
        tx = await conn.begin()
        try:
            await conn.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            with pytest.raises(IntegrityError):
                # Overlaps the student's existing open-ended live period.
                await conn.execute(text(
                    "INSERT INTO student_status_history (id, student_id, status, valid_from, origin) "
                    "VALUES (:id, :sid, 'active', DATE '1990-01-01', 'change')"
                ), {"id": uuid.uuid4(), "sid": sid})
        finally:
            await tx.rollback()


_PHASE2 = ("student_programme_history", "student_intensity_history", "module_enrolment_status_history")


@pytest.mark.parametrize("table", _PHASE2)
async def test_phase2_tables_are_isolated_and_overlap_proof(engine, table):
    async with engine.connect() as conn:
        if await conn.scalar(text(f"SELECT to_regclass('public.{table}')")) is None:
            pytest.skip("Database not migrated to ed2 yet")
        rls = (await conn.execute(text(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t"
        ), {"t": table})).one()
        assert tuple(rls) == (True, True)
        assert await conn.scalar(text(
            "SELECT count(*) FROM pg_policies WHERE tablename = :t AND policyname = 'tenant_isolation'"
        ), {"t": table}) == 1
        assert await conn.scalar(text(
            "SELECT count(*) FROM pg_constraint WHERE conname = :c"
        ), {"c": f"ex_{table}_no_overlap"}) == 1


async def test_phase2_history_matches_cached_values(engine):
    async with engine.connect() as conn:
        if await conn.scalar(text("SELECT to_regclass('public.student_intensity_history')")) is None:
            pytest.skip("Database not migrated to ed2 yet")
        prog_mismatch = await conn.scalar(text(
            "SELECT count(*) FROM student s JOIN student_programme_history h ON h.student_id = s.id "
            "AND h.superseded_by IS NULL AND h.valid_from <= current_date "
            "AND (h.valid_to IS NULL OR h.valid_to > current_date) "
            "WHERE h.programme_id IS DISTINCT FROM s.programme_id"
        ))
        mode_mismatch = await conn.scalar(text(
            "SELECT count(*) FROM student s JOIN student_intensity_history h ON h.student_id = s.id "
            "AND h.superseded_by IS NULL AND h.valid_from <= current_date "
            "AND (h.valid_to IS NULL OR h.valid_to > current_date) "
            "WHERE (CASE WHEN h.intensity_pct >= 100 THEN 'full_time' ELSE 'part_time' END) "
            "<> s.study_mode::text"
        ))
        assert prog_mismatch == 0 and mode_mismatch == 0


async def test_module_enrolments_are_dated_and_consistent(engine):
    async with engine.connect() as conn:
        if await conn.scalar(text("SELECT to_regclass('public.module_enrolment_status_history')")) is None:
            pytest.skip("Database not migrated to ed3 yet")
        undated = await conn.scalar(text("SELECT count(*) FROM module_enrolment WHERE start_date IS NULL"))
        inverted = await conn.scalar(text(
            "SELECT count(*) FROM module_enrolment WHERE end_date IS NOT NULL AND end_date < start_date"))
        mismatched = await conn.scalar(text(
            "SELECT count(*) FROM module_enrolment e JOIN module_enrolment_status_history h "
            "ON h.module_enrolment_id = e.id AND h.superseded_by IS NULL AND h.valid_from <= current_date "
            "AND (h.valid_to IS NULL OR h.valid_to > current_date) WHERE h.status <> e.status"))
        assert (undated, inverted, mismatched) == (0, 0, 0)
