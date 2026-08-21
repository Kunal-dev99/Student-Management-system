"""Identity HTTP endpoints (arch §11.5 — identity and auth)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_principal
from app.core.principal import Principal
from app.db.session import get_session
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.schemas import (
    LoginRequest,
    MeResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    TokenPair,
)
from app.modules.identity.service import IdentityService

auth_router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(tags=["auth"])


def _service(session: AsyncSession) -> IdentityService:
    return IdentityService(IdentityRepository(session))


@auth_router.post("/login", response_model=TokenPair, summary="Password grant")
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    access, refresh, _ = await _service(session).authenticate(body.email, body.password)
    return TokenPair(access_token=access, refresh_token=refresh)


@auth_router.post("/refresh", response_model=TokenPair, summary="Exchange refresh for access")
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)) -> TokenPair:
    access, new_refresh = await _service(session).refresh(body.refresh_token)
    return TokenPair(access_token=access, refresh_token=new_refresh)


@auth_router.post("/logout", summary="Revoke the presented refresh token")
async def logout(body: RefreshRequest, session: AsyncSession = Depends(get_session)) -> dict:
    await _service(session).logout(body.refresh_token)
    return {"data": {"loggedOut": True}}


@auth_router.post("/logout-all", summary="Revoke every session for the current user")
async def logout_all(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
) -> dict:
    revoked = await _service(session).logout_all(principal.user_id)
    return {"data": {"revoked": revoked}}


@auth_router.post("/password-reset/request", summary="Request a password-reset email")
async def password_reset_request(
    body: PasswordResetRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    await _service(session).request_password_reset(body.email)
    # Always 200 — never reveal whether the email is registered.
    return {"data": {"requested": True}}


@auth_router.post("/password-reset/confirm", summary="Set a new password using a reset token")
async def password_reset_confirm(
    body: PasswordResetConfirm, session: AsyncSession = Depends(get_session)
) -> dict:
    await _service(session).confirm_password_reset(body.token, body.new_password)
    return {"data": {"reset": True}}


@me_router.get("/me", response_model=MeResponse, summary="Current principal, roles, permissions")
async def me(principal: Principal = Depends(get_current_principal)) -> MeResponse:
    return MeResponse(
        authenticated=True,
        user_id=principal.user_id,
        email=principal.email,
        person_id=principal.person_id,
        roles=principal.roles,
        permissions=principal.permissions,
    )
