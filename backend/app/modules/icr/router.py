"""ICR module endpoints — read-only views over existing data (arch: additive module)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_read_session
from app.modules.icr.service import IcrService

router = APIRouter(prefix="/icr", tags=["icr"])


@router.get("/overview", summary="ICR cohort overview")
async def overview(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("student.read")),
) -> dict:
    return await IcrService(session).overview()


@router.get("/transfer-viva", summary="Transfer viva (MPhil to PhD upgrade) tracker")
async def transfer_viva(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("progression.read")),
) -> dict:
    return await IcrService(session).transfer_viva()


@router.get("/pathways", summary="Non-clinical and clinical tracks side by side")
async def pathways(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("student.read")),
) -> dict:
    return await IcrService(session).pathways()


@router.get("/funding", summary="ICR funder pillars")
async def funding(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("funding.read")),
) -> dict:
    return await IcrService(session).funding()
