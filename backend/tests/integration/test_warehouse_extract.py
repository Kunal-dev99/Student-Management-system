"""DW-1 — the warehouse extract engine and publisher (SQLite; Postgres specifics are in
test_warehouse_tracking.py).

* Only the acting institution's rows are read (explicit tenant filter; RLS adds a second lock).
* The standard edition carries no personal data; birth_year is derived; the full edition has it.
* Incremental windows return exactly the rows changed in (since, until]; deletions are published.
* Keyset paging never skips or repeats a row, even when many rows share a change time.
* Files match the manifest (row counts, SHA-256), for Parquet and CSV.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pyarrow.parquet as pq
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.db.registry  # noqa: F401
from app.core.tenant_context import tenant_scope
from app.db.base import Base
from app.modules.person.models import Person
from app.modules.student_record.models import Department, Programme
from app.modules.tenant.models import Tenant
from app.modules.warehouse import catalogue, extract
from app.modules.warehouse.models import WarehouseDeletedRow
from app.modules.warehouse.publish import ObjectWindow, publish
from app.modules.warehouse.targets import LocalTarget

A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
B = uuid.UUID("00000000-0000-0000-0000-0000000000b1")
T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db():
    eng = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(eng, expire_on_commit=False)
    async with sm() as s:
        s.add_all([Tenant(id=A, name="A", subdomain="aaa", activated_at=T0),
                   Tenant(id=B, name="B", subdomain="bbb", activated_at=T0)])
        for tid, n in ((A, 5), (B, 3)):
            for i in range(n):
                s.add(Person(tenant_id=tid, given_name=f"G{i}", family_name=f"F{i}",
                             email=f"p{i}@{tid.hex[-2:]}.example.com", date_of_birth=date(1990 + i, 1, 1),
                             updated_at=T0 - timedelta(days=1)))
            s.add(Department(tenant_id=tid, name=f"Dept {tid.hex[-2:]}", code="D1", updated_at=T0 - timedelta(days=1)))
        await s.commit()
    yield sm
    await eng.dispose()


def _person():
    return catalogue.objects(["person"])[0]


async def _all(sm, tid, obj, **kw):
    async with tenant_scope(tid), sm() as s:
        out = []
        async for page in extract.rows(s, tid, obj, **kw):
            out.extend(page)
        return out


@pytest.mark.asyncio
async def test_only_the_acting_institutions_rows_and_no_personal_data(db):
    rows = await _all(db, A, _person(), personal=False, since=None, until=T0)
    assert len(rows) == 5
    assert all("email" not in r and "given_name" not in r and "date_of_birth" not in r for r in rows)
    assert sorted(r["birth_year"] for r in rows) == [1990, 1991, 1992, 1993, 1994]
    assert list(rows[0])[-1] == catalogue.CHANGE_FIELD
    full = await _all(db, A, _person(), personal=True, since=None, until=T0)
    assert {r["email"] for r in full} == {f"p{i}@a1.example.com" for i in range(5)}
    assert len(await _all(db, B, _person(), personal=False, since=None, until=T0)) == 3


@pytest.mark.asyncio
async def test_incremental_window_returns_exactly_the_changed_rows(db):
    async with db() as s:
        p = (await s.execute(Person.__table__.select().where(Person.tenant_id == A).limit(1))).first()
        await s.execute(Person.__table__.update().where(Person.id == p.id).values(updated_at=T0 + timedelta(hours=1)))
        await s.commit()
    changed = await _all(db, A, _person(), personal=False, since=T0, until=T0 + timedelta(hours=2))
    assert [r["id"] for r in changed] == [p.id]
    assert await _all(db, A, _person(), personal=False, since=T0 + timedelta(hours=1), until=T0 + timedelta(hours=2)) == []


@pytest.mark.asyncio
async def test_paging_never_skips_or_repeats_rows_with_equal_change_times(db):
    rows = await _all(db, A, _person(), personal=False, since=None, until=T0, page=2)
    assert len(rows) == 5 and len({r["id"] for r in rows}) == 5


@pytest.mark.parametrize("fmt", ["parquet", "csv"])
@pytest.mark.asyncio
async def test_publish_writes_files_that_match_the_manifest(db, tmp_path, fmt):
    gone = uuid.uuid4()
    async with db() as s:
        s.add(WarehouseDeletedRow(tenant_id=A, table_name="person", row_id=gone, deleted_at=T0 + timedelta(minutes=30)))
        s.add(WarehouseDeletedRow(tenant_id=B, table_name="person", row_id=uuid.uuid4(), deleted_at=T0 + timedelta(minutes=30)))
        await s.commit()
    target = LocalTarget(str(tmp_path))
    windows = [ObjectWindow(_person(), since=T0 - timedelta(days=2)),
               ObjectWindow(catalogue.objects(["department"])[0], since=None)]
    async with tenant_scope(A), db() as s:
        res = await publish(s, tenant_id=A, institution="aaa", publication="Nightly", windows=windows,
                            fmt=fmt, personal=False, target=target, run_id=uuid.uuid4(), until=T0 + timedelta(hours=1))

    run_dir = tmp_path / "aaa" / "nightly" / "20260901T010000Z"
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest == res.manifest and manifest["personalData"] is False
    person = next(o for o in manifest["objects"] if o["name"] == "person")
    assert person["mode"] == "incremental" and person["rows"] == 5 and person["deletedRows"] == 1
    dept = next(o for o in manifest["objects"] if o["name"] == "department")
    assert dept["mode"] == "full" and dept["rows"] == 1 and dept["deletedFiles"] == []
    for f in person["files"] + person["deletedFiles"] + dept["files"]:
        data = (run_dir / f["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == f["sha256"] and len(data) == f["bytes"]

    deleted = (run_dir / person["deletedFiles"][0]["path"]).read_bytes()
    people = (run_dir / person["files"][0]["path"]).read_bytes()
    if fmt == "parquet":
        assert pq.read_table(io.BytesIO(deleted)).column("id").to_pylist() == [str(gone)]
        t = pq.read_table(io.BytesIO(people))
        assert t.num_rows == 5 and "email" not in t.column_names and "birth_year" in t.column_names
        assert str(t.schema.field("_changed_at").type) == "timestamp[us, tz=UTC]"
    else:
        assert list(csv.DictReader(io.StringIO(deleted.decode())))[0]["id"] == str(gone)
        rows = list(csv.DictReader(io.StringIO(people.decode())))
        assert len(rows) == 5 and "email" not in rows[0]
