"""Publications: what an institution publishes, on what schedule, and the record of each run.

A run is full when the publication has never had one, or its ``full_every_days`` has passed;
otherwise each object is incremental from its watermark (the end of its last published window),
and an object with no watermark yet (e.g. just added) is published in full. Watermarks only move
when a run succeeds, so a failed run is simply retried from the same point next time.

The session must be acting as the institution (``tenant_scope``); every query is RLS-scoped.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.modules.warehouse import catalogue, extract
from app.modules.warehouse.files import FORMATS
from app.modules.warehouse.models import WarehousePublication, WarehouseRun, WarehouseWatermark
from app.modules.warehouse.publish import ObjectWindow, publish

FREQUENCIES = ("daily", "hourly")
EDITABLE = ("name", "objects", "file_format", "frequency", "run_at_hour", "personal_data",
            "full_every_days", "enabled")


def _aware(dt: datetime | None) -> datetime | None:
    # SQLite (the test suite) returns naive datetimes; everything here is UTC.
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def next_run(pub: WarehousePublication, after: datetime) -> datetime:
    """The next scheduled time strictly after ``after`` (UTC)."""
    after = after.astimezone(timezone.utc)
    if pub.frequency == "hourly":
        return after.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    candidate = after.replace(hour=pub.run_at_hour, minute=0, second=0, microsecond=0)
    return candidate if candidate > after else candidate + timedelta(days=1)


def _validate(fields: dict) -> None:
    if "objects" in fields and fields["objects"] is not None:
        try:
            catalogue.objects(list(fields["objects"]))
        except ValueError as exc:
            raise ValidationAppError(str(exc)) from exc
        if not fields["objects"]:
            raise ValidationAppError("Choose at least one object, or leave objects empty for all")
    if fields.get("file_format", "parquet") not in FORMATS:
        raise ValidationAppError(f"file_format must be one of {FORMATS}")
    if fields.get("frequency", "daily") not in FREQUENCIES:
        raise ValidationAppError(f"frequency must be one of {FREQUENCIES}")
    if not 0 <= int(fields.get("run_at_hour", 2)) <= 23:
        raise ValidationAppError("run_at_hour is an hour of the day, 0-23 (UTC)")
    if int(fields.get("full_every_days", 7)) < 0:
        raise ValidationAppError("full_every_days can't be negative")
    if "name" in fields and not (fields["name"] or "").strip():
        raise ValidationAppError("A publication needs a name")


class PublicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[WarehousePublication]:
        return list((await self.session.execute(
            select(WarehousePublication).order_by(WarehousePublication.name))).scalars())

    async def get(self, pub_id: uuid.UUID) -> WarehousePublication:
        pub = await self.session.get(WarehousePublication, pub_id)
        if pub is None:
            raise NotFoundError("Publication not found")
        return pub

    async def create(self, *, user_id: uuid.UUID | None, **fields) -> WarehousePublication:
        _validate(fields)
        if (await self.session.execute(select(WarehousePublication.id).where(
                WarehousePublication.name == fields["name"].strip()))).first():
            raise ConflictError(f"A publication named {fields['name']!r} already exists")
        pub = WarehousePublication(**{k: v for k, v in fields.items() if k in EDITABLE},
                                   created_by_user_id=user_id)
        pub.name = pub.name.strip()
        pub.next_run_at = next_run(pub, datetime.now(timezone.utc))
        self.session.add(pub)
        await self.session.commit()
        return pub

    async def update(self, pub_id: uuid.UUID, **fields) -> WarehousePublication:
        _validate(fields)
        pub = await self.get(pub_id)
        for k, v in fields.items():
            if k in EDITABLE:
                setattr(pub, k, v.strip() if k == "name" else v)
        if {"frequency", "run_at_hour", "enabled"} & set(fields):
            pub.next_run_at = next_run(pub, datetime.now(timezone.utc))
        if "personal_data" in fields or "objects" in fields:
            # A different edition or object set starts over with a full extract.
            pub.last_full_at = None
        await self.session.commit()
        return pub

    async def delete(self, pub_id: uuid.UUID) -> None:
        await self.session.delete(await self.get(pub_id))
        await self.session.commit()

    async def runs(self, pub_id: uuid.UUID, limit: int = 50) -> list[WarehouseRun]:
        return list((await self.session.execute(
            select(WarehouseRun).where(WarehouseRun.publication_id == pub_id)
            .order_by(WarehouseRun.started_at.desc()).limit(limit))).scalars())

    async def run(self, pub: WarehousePublication, *, triggered_by: str = "manual", target=None,
                  institution: str | None = None) -> WarehouseRun:
        from app.modules.tenant.models import Tenant
        from app.modules.warehouse.targets import default_target

        now = await extract.database_now(self.session)
        full = pub.last_full_at is None or (
            pub.full_every_days > 0 and now - _aware(pub.last_full_at) >= timedelta(days=pub.full_every_days))
        run = WarehouseRun(publication_id=pub.id, status="running", mode="full" if full else "incremental",
                           triggered_by=triggered_by, started_at=datetime.now(timezone.utc))
        self.session.add(run)
        await self.session.commit()
        run_id, pub_id = run.id, pub.id   # kept: a rollback below expires the loaded objects

        try:
            marks = {} if full else {m.object_name: m for m in (await self.session.execute(
                select(WarehouseWatermark).where(WarehouseWatermark.publication_id == pub.id))).scalars()}
            windows = [ObjectWindow(o, None if o.name not in marks else extract.window_start(_aware(marks[o.name].high_water)))
                       for o in catalogue.objects(pub.objects)]
            if institution is None:
                institution = await self.session.scalar(select(Tenant.subdomain).where(Tenant.id == pub.tenant_id))
            result = await publish(self.session, tenant_id=pub.tenant_id, institution=institution or "institution",
                                   publication=pub.name, windows=windows, fmt=pub.file_format,
                                   personal=pub.personal_data, target=target or default_target(),
                                   run_id=run.id, until=now)
            existing = {m.object_name: m for m in (await self.session.execute(
                select(WarehouseWatermark).where(WarehouseWatermark.publication_id == pub.id))).scalars()}
            for name, high in result.high_water.items():
                if name in existing:
                    existing[name].high_water = high
                else:
                    self.session.add(WarehouseWatermark(publication_id=pub.id, object_name=name, high_water=high))
            if full:
                pub.last_full_at = now
            run.status, run.location, run.manifest, run.window_to = "succeeded", result.location, result.manifest, now
        except Exception as exc:  # recorded on the run; the watermarks stay where they were
            await self.session.rollback()
            run = await self.session.get(WarehouseRun, run_id)
            pub = await self.session.get(WarehousePublication, pub_id)
            run.status, run.error = "failed", f"{type(exc).__name__}: {str(exc)[:500]}"
        run.finished_at = datetime.now(timezone.utc)
        if triggered_by == "schedule":
            pub.next_run_at = next_run(pub, run.finished_at)
        await self.session.commit()
        return run

    async def run_due(self, *, target=None) -> list[WarehouseRun]:
        """Every enabled publication whose time has come (the worker calls this per institution)."""
        now = datetime.now(timezone.utc)
        due = list((await self.session.execute(select(WarehousePublication).where(
            WarehousePublication.enabled.is_(True), WarehousePublication.next_run_at <= now))).scalars())
        return [await self.run(p, triggered_by="schedule", target=target) for p in due]
