"""Audit trail viewer (arch §17). Read-only; guarded by `audit.read`."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_permission
from app.db.session import get_read_session
from app.modules.audit.models import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", summary="Audit trail (filterable)")
async def list_audit(
    entityType: str | None = Query(None),
    entityId: uuid.UUID | None = Query(None),
    actorEmail: str | None = Query(None),
    fromDate: date | None = Query(None, description="inclusive"),
    toDate: date | None = Query(None, description="inclusive"),
    limit: int = Query(100, le=500),
    session: AsyncSession = Depends(get_read_session),
    _=Depends(require_permission("audit.read")),
) -> list[dict]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if entityType:
        stmt = stmt.where(AuditLog.entity_type == entityType)
    if entityId:
        stmt = stmt.where(AuditLog.entity_id == entityId)
    if actorEmail:
        stmt = stmt.where(AuditLog.actor_email == actorEmail)
    if fromDate:
        stmt = stmt.where(AuditLog.created_at >= fromDate)
    if toDate:
        stmt = stmt.where(AuditLog.created_at < toDate + timedelta(days=1))
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "actorEmail": r.actor_email,
            "action": r.action,
            "method": r.method,
            "entityType": r.entity_type,
            "entityId": str(r.entity_id) if r.entity_id else None,
            "statusCode": r.status_code,
            "requestId": r.request_id,
            "detail": r.detail,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
