"""Shared FastAPI dependencies: DB session, current principal, permission guard (arch §6.5, §12).

Authorization fails closed — a request with no matching permission is denied.
"""
from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, PermissionError
from app.core.principal import Principal
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
    return await service.principal_from_access_token(creds.credentials)


def require_permission(code: str):
    """Dependency factory — guards a route with a single permission code."""

    async def _guard(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not principal.has_permission(code):
            raise PermissionError(f"Missing permission: {code}")
        return principal

    return _guard
