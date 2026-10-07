"""Benchmark: profile-aware custom attribute loading (custom attribute governance, Phase 5).

Builds a synthetic institution in an in-memory SQLite database (never touches a real one):
``--students`` students, ``--live`` live custom attributes and ``--retired`` retired ones, each with
a value for every student. A return maps ``--mapped`` of the live attributes. It then times
``StatutoryEngine.build_records`` and measures its peak Python memory two ways:

- all-live — the pre-Phase-5 behaviour: every live attribute loaded for every student
- profile  — Phase 5: only the attributes the return maps

and checks both produce the same values for the mapped attributes.

    python scripts/bench_custom_attributes.py --students 5000 --live 100 --retired 50 --mapped 3

SQLite in memory understates real database I/O, so read the ratio, not the absolute numbers.
"""
from __future__ import annotations

import argparse
import asyncio
import time
import tracemalloc
import uuid
from datetime import date

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import app  # noqa: F401  registers every model
from app.modules.exports.statutory import StatutoryEngine
from app.modules.person.models import Person
from app.modules.student_record.constants import StudentStatus, StudyMode
from app.modules.student_record.models import Programme, Student, StudentCustomField, StudentCustomValue

TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def seed(sm, students: int, live: int, retired: int) -> list[str]:
    async with sm() as s:
        prog = Programme(name="PhD", code="PHD")
        s.add(prog)
        await s.flush()
        people = [{"id": uuid.uuid4(), "tenant_id": TENANT, "given_name": f"G{i}", "family_name": f"F{i}"}
                  for i in range(students)]
        await s.execute(insert(Person), people)
        studs = [{"id": uuid.uuid4(), "tenant_id": TENANT, "person_id": p["id"], "student_ref": f"S{i:06d}",
                  "programme_id": prog.id, "start_date": date(2025, 10, 1), "expected_end_date": date(2029, 9, 30),
                  "study_mode": StudyMode.full_time, "status": StudentStatus.active}
                 for i, p in enumerate(people)]
        await s.execute(insert(Student), studs)
        fields = [{"id": uuid.uuid4(), "tenant_id": TENANT, "key": f"attr_{i:03d}", "label": f"Attr {i}",
                   "data_type": "code", "reason": "bench", "status": "active" if i < live else "retired",
                   "track_history": False}
                  for i in range(live + retired)]
        await s.execute(insert(StudentCustomField), fields)
        batch = []
        for f in fields:
            for st in studs:
                batch.append({"id": uuid.uuid4(), "tenant_id": TENANT, "custom_field_id": f["id"],
                              "student_id": st["id"], "value": f"{f['key']}:{st['student_ref']}"})
                if len(batch) >= 20_000:
                    await s.execute(insert(StudentCustomValue), batch)
                    batch = []
        if batch:
            await s.execute(insert(StudentCustomValue), batch)
        await s.commit()
        return [f["key"] for f in fields[:live]]


async def measure(sm, custom_keys) -> tuple[float, float, dict, list]:
    async with sm() as s:
        eng = StatutoryEngine(s)
        tracemalloc.start()
        t0 = time.perf_counter()
        records = await eng.build_records(custom_keys=custom_keys)
        ms = (time.perf_counter() - t0) * 1000
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return ms, peak / 1_048_576, eng.last_build_stats, records


async def bench_catalogue(sm) -> None:
    """Governance screens against the whole catalogue (Phase 7 large-catalogue check): the
    catalogue's usage counts, the review dashboard's health signals, and a new request's
    duplicate check — each should stay a handful of queries however many attributes exist."""
    from sqlalchemy import event

    from app.modules.student_record.custom_attr_assessment import assess
    from app.modules.student_record.custom_attr_usage import health
    from app.modules.student_record.custom_fields import CustomFieldService

    async with sm() as s:
        fields = await CustomFieldService(s).list_fields()
        statements = []
        sync_engine = s.bind.sync_engine

        def count(*_a, **_k):
            statements.append(1)

        event.listen(sync_engine, "before_cursor_execute", count)
        print(f"\nGovernance screens over {len(fields)} attributes:")
        for label, run in (
            ("catalogue usage counts", lambda: CustomFieldService(s).usage(fields)),
            ("dashboard health + review rules", lambda: health(s, fields)),
            ("new request duplicate/HESA check", lambda: assess(s, label="Care leaver status", reason="HESA CARELEAVER")),
        ):
            statements.clear()
            t0 = time.perf_counter()
            await run()
            print(f"  {label:34} {(time.perf_counter() - t0) * 1000:8.0f} ms  {len(statements):3} queries")
        event.remove(sync_engine, "before_cursor_execute", count)


async def main(a) -> None:
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    t0 = time.perf_counter()
    live_keys = await seed(sm, a.students, a.live, a.retired)
    print(f"Seeded {a.students} students, {a.live} live + {a.retired} retired attributes, "
          f"{a.students * (a.live + a.retired):,} values in {time.perf_counter() - t0:.1f}s")
    mapped = live_keys[: a.mapped]
    if a.catalogue:
        await bench_catalogue(sm)
        await eng.dispose()
        return

    rows = []
    for label, keys in (("all-live (before)", None), (f"profile, {a.mapped} mapped (after)", set(mapped))):
        best = None
        for _ in range(a.repeat):
            ms, mb, stats, records = await measure(sm, keys)
            best = (ms, mb, stats, records) if best is None or ms < best[0] else best
        rows.append((label, *best))

    (_, _, _, _, full), (_, _, _, _, scoped) = rows
    same = all(f["custom"].get(k) == s_["custom"].get(k) for f, s_ in zip(full, scoped) for k in mapped)
    print(f"\n{'mode':32} {'build ms':>10} {'peak MiB':>10} {'values loaded':>15} {'keys/record':>12}")
    for label, ms, mb, stats, records in rows:
        print(f"{label:32} {ms:10.0f} {mb:10.1f} {stats['customValuesLoaded']:15,} {len(records[0]['custom']):12}")
    (_, ms0, mb0, *_), (_, ms1, mb1, *_) = rows
    print(f"\nSpeed-up {ms0 / ms1:.1f}x, peak memory {mb0 / mb1:.1f}x lower. "
          f"Mapped values identical: {same}.")
    await eng.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--students", type=int, default=3000)
    p.add_argument("--live", type=int, default=100)
    p.add_argument("--retired", type=int, default=50)
    p.add_argument("--mapped", type=int, default=3)
    p.add_argument("--repeat", type=int, default=2)
    p.add_argument("--catalogue", action="store_true",
                   help="time the governance screens over the catalogue instead of build_records")
    asyncio.run(main(p.parse_args()))
