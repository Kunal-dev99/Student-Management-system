"""Read catalogue objects for one institution: all rows, or the rows changed in a time window.

Runs on the caller's session, which must be acting as the institution (``tenant_scope``): row-level
security limits every read to it, and each query also filters on ``tenant_id`` explicitly (the
second lock, and the only one on SQLite in the tests).

Incremental windows are ``(since, until]`` on the change column. ``until`` is the database's clock
at the start of the run; the next run starts from it minus ``OVERLAP``, because a transaction that
was still open at ``until`` commits rows stamped earlier than ``until``. Rows in the overlap are
published twice, so consumers upsert on ``id`` (the manifest says so).

Pages are keyset-paginated on ``(change column, id)``, so large tables stream in fixed memory and a
page boundary never skips or repeats a row.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.database  # noqa: F401  (the listener that publishes the acting institution)
from app.db.tenant_views import Published
from app.modules.warehouse.catalogue import CHANGE_COLUMN, CHANGE_FIELD, DERIVED, _table

OVERLAP = timedelta(minutes=5)
PAGE = 5000


async def database_now(session: AsyncSession) -> datetime:
    from datetime import timezone

    value = await session.scalar(select(text("CURRENT_TIMESTAMP")))
    if isinstance(value, str):  # SQLite returns text
        value = datetime.fromisoformat(value)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _select(obj: Published, personal: bool):
    table = _table(obj)
    cols = [table.c[c] for c in obj.columns if c in table.c]
    if personal:
        cols += [table.c[c] for c in obj.personal if c in table.c]
    else:
        # Fetch the source of each derived column; it is turned into the derived value and dropped.
        cols += [table.c[DERIVED[n][0]].label(f"__src_{n}") for n, _ in obj.derived
                 if n in DERIVED and DERIVED[n][0] in table.c]
    cols.append(table.c[CHANGE_COLUMN].label(CHANGE_FIELD))
    return table, select(*cols)


def _shape(row: dict, obj: Published) -> dict:
    for name, _ in obj.derived:
        key = f"__src_{name}"
        if key in row:
            row[name] = DERIVED[name][1](row.pop(key))
    # The change column goes last, as in the published column list.
    row[CHANGE_FIELD] = row.pop(CHANGE_FIELD)
    return row


async def rows(session: AsyncSession, tenant_id: uuid.UUID, obj: Published, *, personal: bool,
               since: datetime | None, until: datetime, page: int = PAGE,
               after: tuple | None = None) -> AsyncIterator[list[dict]]:
    """Yield pages of published rows changed in ``(since, until]`` (all rows up to ``until`` when
    ``since`` is None), oldest change first. ``after`` = (change time, id) resumes after that row."""
    table, base = _select(obj, personal)
    change, key = table.c[CHANGE_COLUMN], table.c.id
    base = base.where(table.c.tenant_id == tenant_id, change <= until)
    if since is not None:
        base = base.where(change > since)
    while True:
        q = base
        if after is not None:
            q = q.where(or_(change > after[0], and_(change == after[0], key > after[1])))
        batch = [dict(r) for r in (await session.execute(q.order_by(change, key).limit(page))).mappings()]
        if not batch:
            return
        last = batch[-1]
        after = (last[CHANGE_FIELD], last["id"])
        yield [_shape(r, obj) for r in batch]
        if len(batch) < page:
            return


async def deleted(session: AsyncSession, tenant_id: uuid.UUID, obj: Published, *,
                  since: datetime | None, until: datetime) -> list[dict]:
    """Ids of rows deleted from the object's table in ``(since, until]``. A full extract carries
    none: the warehouse replaces the object, so anything absent is gone."""
    if since is None:
        return []
    from app.modules.warehouse.models import WarehouseDeletedRow as D

    q = select(D.row_id, D.deleted_at).where(
        D.tenant_id == tenant_id, D.table_name == obj.table, D.deleted_at > since, D.deleted_at <= until,
    ).order_by(D.deleted_at)
    return [{"id": r.row_id, "deleted_at": r.deleted_at} for r in await session.execute(q)]


def window_start(previous_until: datetime | None) -> datetime | None:
    return None if previous_until is None else previous_until - OVERLAP
