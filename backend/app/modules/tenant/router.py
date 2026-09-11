"""Public tenant directory — powers the tenant selector on the login page.

Deliberately unauthenticated: the login screen is pre-auth, and the tenant list is
non-sensitive metadata (names, subdomains, public branding). Only active tenants are
returned; inactive/deactivated ones are hidden.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_read_session
from app.modules.tenant.models import Tenant

router = APIRouter(prefix="/tenants", tags=["tenant"])


@router.get("", summary="Public list of active tenants — feeds the login-page selector")
async def list_tenants(session: AsyncSession = Depends(get_read_session)) -> list[dict]:
    rows = (await session.execute(
        select(Tenant)
        .where(Tenant.activated_at.is_not(None), Tenant.deactivated_at.is_(None))
        .order_by(Tenant.name)
    )).scalars().all()
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "subdomain": t.subdomain,
            "logoText": (t.branding or {}).get("logoText"),
            "primaryColor": (t.branding or {}).get("primaryColor"),
            "tagline": (t.branding or {}).get("tagline"),
        }
        for t in rows
    ]
