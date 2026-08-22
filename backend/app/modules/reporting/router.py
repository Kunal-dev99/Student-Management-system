"""Reporting HTTP endpoints (arch §11.5 — reporting)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.core.principal import Principal
from app.db.session import get_read_session, get_session
from app.modules.reporting.analytics import AnalyticsService
from app.modules.reporting.repository import ReportingRepository
from app.modules.reporting.service import ReportingService

router = APIRouter(prefix="/dashboards", tags=["reporting"])
reports_router = APIRouter(prefix="/reports", tags=["reporting"])


@reports_router.get("/pgr-enterprise-360", summary="PGR Enterprise 360 — one population, five lenses")
async def pgr_enterprise_360(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("reporting.read")),
) -> dict:
    return await AnalyticsService(session).enterprise_360()


@reports_router.get("/funding-integrity", summary="Students whose funding chain has problems")
async def funding_integrity(
    severity: str | None = None,
    session: AsyncSession = Depends(get_read_session),
    principal: Principal = Depends(require_permission("funding.read")),
) -> dict:
    """Phase 6.3 — cohort-wide funding lineage validation, row-scoped like every other read."""
    from app.modules.funding.lineage import FundingLineageService
    from app.modules.student_record.router import scoped_ids

    allowed = await scoped_ids(principal, session)
    return await FundingLineageService(session).cohort_integrity(
        allowed_ids=allowed, severity=severity
    )


@reports_router.get("/analytics", summary="Risk, completion, and forecasting analytics")
async def analytics(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("reporting.read")),
) -> dict:
    return await AnalyticsService(session).analytics()


def _svc(session: AsyncSession) -> ReportingService:
    return ReportingService(ReportingRepository(session))


@router.get("/supervisor", summary="Supervisor caseload dashboard (own supervisees)")
async def supervisor(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_permission("student.read")),
) -> dict:
    return await _svc(session).supervisor(principal.person_id)


@router.get("/executive", summary="Executive dashboard read model")
async def executive(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> dict:
    return await _svc(session).executive()


@router.get("/administrator", summary="Administrator dashboard read model")
async def administrator(
    session: AsyncSession = Depends(get_session),
    _=Depends(require_permission("reporting.read")),
) -> dict:
    return await _svc(session).administrator()
