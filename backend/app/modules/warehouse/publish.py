"""Publish catalogue objects for one institution: files plus a manifest, in one run folder.

    <institution>/<publication>/<run timestamp>/
        manifest.json
        <object>.parquet | .csv               rows changed in the window (all rows when full)
        <object>__deleted.parquet | .csv      ids deleted in the window (incremental only)

The manifest is written last, so a loader that waits for ``manifest.json`` never reads a half-written
run. It lists every file with its row count, size and SHA-256, the window per object, and the schema.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tenant_views import Published
from app.modules.warehouse import catalogue, extract, files

PART_ROWS = 100_000      # one file per object up to this many rows, then part files


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "publication"


@dataclass
class ObjectWindow:
    obj: Published
    since: datetime | None          # None = full


@dataclass
class Result:
    location: str
    manifest: dict
    high_water: dict[str, datetime] = field(default_factory=dict)


async def publish(session: AsyncSession, *, tenant_id: uuid.UUID, institution: str, publication: str,
                  windows: list[ObjectWindow], fmt: str, personal: bool, target, run_id: uuid.UUID,
                  until: datetime | None = None) -> Result:
    until = until or await extract.database_now(session)
    ext = "parquet" if fmt == "parquet" else "csv"
    content_type = "application/vnd.apache.parquet" if fmt == "parquet" else "text/csv"
    prefix = f"{slug(institution)}/{slug(publication)}/{until.strftime('%Y%m%dT%H%M%SZ')}"
    objects_out, high_water = [], {}

    for w in windows:
        cols = catalogue.columns(w.obj, personal)
        written, total, part, buffer = [], 0, 0, []

        def flush(last: bool = False):
            nonlocal part, buffer
            if not buffer and (part or not last):
                return
            name = f"{w.obj.name}.{ext}" if (last and part == 0) else f"{w.obj.name}-part-{part:04d}.{ext}"
            data = files.write(buffer, cols, fmt)
            target.put(f"{prefix}/{name}", data, content_type)
            written.append({"path": name, "rows": len(buffer), "bytes": len(data),
                            "sha256": hashlib.sha256(data).hexdigest()})
            part += 1
            buffer = []

        async for page in extract.rows(session, tenant_id, w.obj, personal=personal, since=w.since, until=until):
            buffer.extend(page)
            total += len(page)
            if len(buffer) >= PART_ROWS:
                flush()
        flush(last=True)

        gone = await extract.deleted(session, tenant_id, w.obj, since=w.since, until=until)
        deleted_files = []
        if gone:
            data = files.write(gone, files.DELETED_COLUMNS, fmt)
            name = f"{w.obj.name}__deleted.{ext}"
            target.put(f"{prefix}/{name}", data, content_type)
            deleted_files.append({"path": name, "rows": len(gone), "bytes": len(data),
                                  "sha256": hashlib.sha256(data).hexdigest()})

        high_water[w.obj.name] = until
        objects_out.append({
            "name": w.obj.name,
            "mode": "full" if w.since is None else "incremental",
            "windowFrom": w.since.isoformat() if w.since else None,
            "windowTo": until.isoformat(),
            "rows": total,
            "deletedRows": len(gone),
            "files": written,
            "deletedFiles": deleted_files,
            "schema": catalogue.describe(w.obj, personal),
        })

    manifest = {
        "formatVersion": 1,
        "institution": institution,
        "publication": publication,
        "runId": str(run_id),
        "generatedAt": until.isoformat(),
        "format": fmt,
        "personalData": personal,
        "loading": ("Upsert each object's rows on 'id'. Incremental windows overlap by "
                    f"{int(extract.OVERLAP.total_seconds() // 60)} minutes, so a row can appear in two "
                    "runs. Delete the ids listed in '<object>__deleted' files. A full object replaces "
                    "what you hold for it."),
        "objects": objects_out,
    }
    target.put(f"{prefix}/manifest.json", json.dumps(manifest, indent=2).encode(), "application/json")
    return Result(location=target.location(prefix), manifest=manifest, high_water=high_water)
