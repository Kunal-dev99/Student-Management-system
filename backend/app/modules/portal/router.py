"""Student portal endpoint (arch §13.3). Self-service; scoped to the principal."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_principal
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.portal.service import PortalService

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/journey", summary="My journey (the signed-in person's own lifecycle)")
async def my_journey(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    return await PortalService(session).student_journey(principal)
