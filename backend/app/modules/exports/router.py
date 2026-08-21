"""Export HTTP endpoints (arch §11.5, §13.4)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_session
from app.modules.exports.schemas import ExportJobOut, ExportRequest
from app.modules.exports.service import ExportService

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("", response_model=ExportJobOut, status_code=201, summary="Start an export job")
async def create_export(
    body: ExportRequest,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> ExportJobOut:
    return ExportJobOut.model_validate(await ExportService(session).create_and_run(body.kind))


@router.get("", response_model=list[ExportJobOut], summary="Recent export jobs")
async def list_exports(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> list[ExportJobOut]:
    return [ExportJobOut.model_validate(j) for j in await ExportService(session).list_recent()]


@router.get("/{job_id}", response_model=ExportJobOut, summary="Export job status")
async def get_export(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> ExportJobOut:
    return ExportJobOut.model_validate(await ExportService(session).get(job_id))


@router.get("/{job_id}/download", summary="Download the export file")
async def download_export(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
):
    job = await ExportService(session).get(job_id)
    content = job.content or ""
    return Response(
        content=content, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{job.filename or "export.csv"}"'},
    )
