"""Shared FastAPI dependencies: DB session, current principal, permission guard (arch §6.5, §12).

Authorization fails closed — a request with no matching permission is denied.
"""
from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, PermissionError
from app.core.principal import Principal
from app.core.tenant_context import set_current_tenant
from app.db.session import get_session
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.service import IdentityService

_bearer = HTTPBearer(auto_error=False)


async def get_current_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    if creds is None or not creds.credentials:
        raise AuthError("Authentication required")
    service = IdentityService(IdentityRepository(session))
    principal = await service.principal_from_access_token(creds.credentials)
    # MT-1 — set the Postgres session-local tenant context if the principal carries one.
    # No-op today (RLS policies land in Phase 2), but the plumbing is now here so the
    # switch is a one-line change per table when we're ready.
    await _set_tenant_context(session, principal)
    return principal


async def _set_tenant_context(session: AsyncSession, principal: Principal) -> None:
    """Set the acting tenant for this request (MT-2).

    Two sinks read the tenant: the ORM (insert-time stamping via ``TenantMixin``, from the
    ContextVar) and Postgres RLS (the `app.current_tenant` session variable). We always set
    the ContextVar so new rows are stamped even on SQLite; the session variable is set only
    on Postgres, where `SET LOCAL` and RLS exist.
    """
    # Always available to the ORM default, on any dialect.
    set_current_tenant(principal.tenant_id)

    if principal.tenant_id is None:
        return
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return
    from sqlalchemy import text as _text
    # SET LOCAL scopes the setting to the current transaction — perfect for a per-request
    # tenant. `set_config(..., true)` is the parameterised form (SET LOCAL doesn't bind).
    await session.execute(
        _text("SELECT set_config('app.current_tenant', :tid, true)")
        .bindparams(tid=str(principal.tenant_id))
    )


def require_permission(code: str):
    """Dependency factory — guards a route with a single permission code."""

    async def _guard(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not principal.has_permission(code):
            raise PermissionError(f"Missing permission: {code}")
        return principal

    return _guard
