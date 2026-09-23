"""Shared FastAPI dependencies: DB session, current principal, permission guard (arch §6.5, §12).

Authorization fails closed — a request with no matching permission is denied.
"""
from __future__ import annotations

import uuid

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, PermissionError
from app.core.principal import Principal
from app.core.tenant_context import set_current_tenant
from app.core.tenant_resolver import resolve_tenant_id_for_host
from app.db.session import get_session
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.service import IdentityService

_bearer = HTTPBearer(auto_error=False)


async def get_current_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    if creds is None or not creds.credentials:
        raise AuthError("Authentication required")
    service = IdentityService(IdentityRepository(session))
    principal = await service.principal_from_access_token(creds.credentials)
    # MT-5 — the acting tenant is resolved from the request Host (subdomain) and reconciled
    # with the token's tenant; the URL's tenant wins, and a token for another tenant cannot
    # be replayed against this subdomain. Neutral/dev hosts resolve to None, so this is a
    # no-op on localhost and falls back to the token tenant.
    host_tid = await resolve_tenant_id_for_host(request.headers.get("host", ""))
    effective = _reconcile_tenant(host_tid, principal.tenant_id)
    await _apply_tenant_context(session, effective)
    return principal


def _reconcile_tenant(
    host_tid: uuid.UUID | None, token_tid: uuid.UUID | None
) -> uuid.UUID | None:
    """The effective tenant for this request: the host's, falling back to the token's.

    If both are present and disagree, the token is being used on a subdomain it does not
    belong to — a cross-tenant attempt — so we refuse.
    """
    if host_tid is not None and token_tid is not None and host_tid != token_tid:
        raise PermissionError("This account does not belong to this tenant")
    return host_tid or token_tid


async def _apply_tenant_context(session: AsyncSession, tenant_id: uuid.UUID | None) -> None:
    """Publish the acting tenant to the ORM (ContextVar, any dialect) and to Postgres RLS
    (the `app.current_tenant` session variable, set transaction-local via SET LOCAL)."""
    # Always available to the ORM default, on any dialect.
    set_current_tenant(tenant_id)

    if tenant_id is None:
        return
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return
    from sqlalchemy import text as _text
    await session.execute(
        _text("SELECT set_config('app.current_tenant', :tid, true)")
        .bindparams(tid=str(tenant_id))
    )


def require_permission(code: str):
    """Dependency factory — guards a route with a single permission code."""

    async def _guard(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not principal.has_permission(code):
            raise PermissionError(f"Missing permission: {code}")
        return principal

    return _guard
