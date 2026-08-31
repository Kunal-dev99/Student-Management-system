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


@reports_router.get("/funding-cashflow", summary="Finance lens on stipend payments (W4)")
async def funding_cashflow(
    windowFrom: str | None = None,
    windowTo: str | None = None,
    session: AsyncSession = Depends(get_read_session),
    principal: Principal = Depends(require_permission("funding.read")),
) -> dict:
    """W4 — the Finance-facing cut of the funding-integrity screen.

    Cashflow totals for a window plus three actionable lists: Finance-rejected (HELD),
    approved-but-overdue, and paid-without-Finance-reference.
    """
    from datetime import date as _date
    from app.modules.funding.finance_lens import FinanceLensService
    from app.modules.student_record.router import scoped_ids

    allowed = await scoped_ids(principal, session)
    wf = _date.fromisoformat(windowFrom) if windowFrom else None
    wt = _date.fromisoformat(windowTo) if windowTo else None
    return await FinanceLensService(session).snapshot(
        allowed_ids=allowed, window_from=wf, window_to=wt,
    )


@reports_router.get("/supervisor-workforce", summary="Workforce lens — supervisor capacity institution-wide (W5)")
async def supervisor_workforce(
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("student.read")),
) -> dict:
    """W5 — institution-wide supervisor caseload / capacity / availability snapshot."""
    from app.modules.supervision.workforce_lens import WorkforceLensService

    return await WorkforceLensService(session).snapshot()


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
