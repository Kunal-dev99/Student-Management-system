"""Public tenant directory — powers the tenant selector on the login page.

Deliberately unauthenticated: the login screen is pre-auth. Only active tenants are returned.

It must not publish the customer list in production:

* Subdomain deployments (TENANT_BASE_DOMAIN set): only the institution the address names;
  ``icr.<base>`` gives ICR, and the bare base domain gives the default deployment.
* Single-address SaaS in production: nothing. The email alone says which institution a user
  belongs to, so the login page needs no selector.
* Local dev, demos and staging: every active institution, so the branding selector works.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_read_session
from app.modules.tenant.models import Tenant

router = APIRouter(prefix="/tenants", tags=["tenant"])


@router.get("", summary="Public list of active tenants — feeds the login-page selector")
async def list_tenants(request: Request, session: AsyncSession = Depends(get_read_session)) -> list[dict]:
    from app.core.config import get_settings
    from app.core.tenant_context import DEFAULT_TENANT_ID
    from app.core.tenant_resolver import tenant_for_request

    query = select(Tenant).where(Tenant.activated_at.is_not(None), Tenant.deactivated_at.is_(None))
    settings = get_settings()
    if settings.tenant_base_domain:
        query = query.where(Tenant.id == (await tenant_for_request(request) or DEFAULT_TENANT_ID))
    elif settings.app_env == "production":
        return []
    rows = (await session.execute(query.order_by(Tenant.name))).scalars().all()
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
