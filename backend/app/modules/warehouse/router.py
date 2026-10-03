"""Data warehouse export — administration: the catalogue, publications and their runs.

Managing publications needs ``admin.configure``; reading the catalogue and run history needs
``reporting.read``. Everything is scoped to the caller's institution.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_read_session, get_session
from app.modules.warehouse import catalogue
from app.modules.warehouse.models import WarehousePublication, WarehouseRun
from app.modules.warehouse.service import PublicationService

router = APIRouter(prefix="/warehouse", tags=["warehouse"])


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PublicationIn(_Camel):
    name: str = Field(min_length=1, max_length=120)
    objects: list[str] | None = None
    file_format: str = "parquet"
    frequency: str = "daily"
    run_at_hour: int = 2
    personal_data: bool = False
    full_every_days: int = 7
    enabled: bool = True


class PublicationPatch(_Camel):
    name: str | None = None
    objects: list[str] | None = None
    file_format: str | None = None
    frequency: str | None = None
    run_at_hour: int | None = None
    personal_data: bool | None = None
    full_every_days: int | None = None
    enabled: bool | None = None


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _pub(p: WarehousePublication) -> dict:
    return {
        "id": str(p.id), "name": p.name, "objects": p.objects, "fileFormat": p.file_format,
        "frequency": p.frequency, "runAtHour": p.run_at_hour, "personalData": p.personal_data,
        "fullEveryDays": p.full_every_days, "enabled": p.enabled,
        "nextRunAt": _iso(p.next_run_at), "lastFullAt": _iso(p.last_full_at),
    }


def _run(r: WarehouseRun, manifest: bool = False) -> dict:
    out = {
        "id": str(r.id), "publicationId": str(r.publication_id), "status": r.status, "mode": r.mode,
        "triggeredBy": r.triggered_by, "startedAt": _iso(r.started_at), "finishedAt": _iso(r.finished_at),
        "windowTo": _iso(r.window_to), "location": r.location, "error": r.error,
        "rows": sum(o["rows"] for o in (r.manifest or {}).get("objects", [])) if r.manifest else None,
        "deletedRows": sum(o["deletedRows"] for o in (r.manifest or {}).get("objects", [])) if r.manifest else None,
    }
    if manifest:
        out["manifest"] = r.manifest
    return out


@router.get("/catalogue", summary="Published objects and their columns (standard and full-detail editions)")
async def get_catalogue(_=Depends(require_permission("reporting.read"))) -> list[dict]:
    out = []
    for o in catalogue.objects():
        std, full = catalogue.describe(o, False), catalogue.describe(o, True)
        std["personalColumns"] = [c["name"] for c in full["columns"] if c["personal"]]
        out.append(std)
    return out


@router.get("/publications", summary="This institution's scheduled publications")
async def list_publications(session: AsyncSession = Depends(get_read_session),
                            _=Depends(require_permission("reporting.read"))) -> list[dict]:
    return [_pub(p) for p in await PublicationService(session).list()]


@router.post("/publications", status_code=201, summary="Create a scheduled publication")
async def create_publication(body: PublicationIn, session: AsyncSession = Depends(get_session),
                             principal=Depends(require_permission("admin.configure"))) -> dict:
    return _pub(await PublicationService(session).create(user_id=principal.user_id, **body.model_dump()))


@router.patch("/publications/{pub_id}", summary="Change a publication")
async def update_publication(pub_id: uuid.UUID, body: PublicationPatch, session: AsyncSession = Depends(get_session),
                             _=Depends(require_permission("admin.configure"))) -> dict:
    fields = body.model_dump(exclude_unset=True)
    return _pub(await PublicationService(session).update(pub_id, **fields))


@router.delete("/publications/{pub_id}", status_code=204, summary="Delete a publication (its files stay)")
async def delete_publication(pub_id: uuid.UUID, session: AsyncSession = Depends(get_session),
                             _=Depends(require_permission("admin.configure"))) -> Response:
    await PublicationService(session).delete(pub_id)
    return Response(status_code=204)


@router.post("/publications/{pub_id}/run", summary="Run a publication now")
async def run_publication(pub_id: uuid.UUID, session: AsyncSession = Depends(get_session),
                          _=Depends(require_permission("admin.configure"))) -> dict:
    svc = PublicationService(session)
    return _run(await svc.run(await svc.get(pub_id), triggered_by="manual"), manifest=True)


@router.get("/publications/{pub_id}/runs", summary="A publication's recent runs")
async def list_runs(pub_id: uuid.UUID, session: AsyncSession = Depends(get_read_session),
                    _=Depends(require_permission("reporting.read"))) -> list[dict]:
    svc = PublicationService(session)
    await svc.get(pub_id)
    return [_run(r) for r in await svc.runs(pub_id)]


@router.get("/runs/{run_id}", summary="One run, with its manifest")
async def get_run(run_id: uuid.UUID, session: AsyncSession = Depends(get_read_session),
                  _=Depends(require_permission("reporting.read"))) -> dict:
    from app.core.errors import NotFoundError

    run = await session.get(WarehouseRun, run_id)
    if run is None:
        raise NotFoundError("Run not found")
    return _run(run, manifest=True)
