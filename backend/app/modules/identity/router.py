"""Identity HTTP endpoints (arch §11.5 — identity and auth)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, Request
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


@asynccontextmanager
async def _pre_auth_scope(request: Request, session: AsyncSession, *, email: str | None = None,
                          refresh_token: str | None = None, reset_token: str | None = None):
    """Sign-in and token flows run before the institution is known, and RLS is fail-closed.

    * On an institution's subdomain the lookup is scoped to that institution, so an email from
      another institution is simply "not found".
    * On a single shared address (the SaaS deployment) the email or token itself names the
      institution, found through the narrow lookup functions in ``app.core.pre_auth``. No bypass
      is used, so this also works under the restricted app login (pgr_app).
    If nothing matches, no institution is set and the service answers "not found" as usual."""
    from app.core import pre_auth
    from app.core.tenant_context import set_current_tenant
    from app.core.tenant_resolver import tenant_for_request

    tid = await tenant_for_request(request)
    if tid is None:
        if email is not None:
            tid = await pre_auth.tenant_of_email(session, email)
        elif refresh_token is not None:
            tid = await pre_auth.tenant_of_refresh_token(session, refresh_token)
        elif reset_token is not None:
            tid = await pre_auth.tenant_of_reset_token(session, reset_token)
        await session.rollback()   # end the lookup; the next transaction runs as the institution
    if tid is not None:
        set_current_tenant(tid)
    yield


@auth_router.post("/login", response_model=TokenPair, summary="Password grant")
async def login(body: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)) -> TokenPair:
    async with _pre_auth_scope(request, session, email=body.email):
        access, refresh, _ = await _service(session).authenticate(body.email, body.password)
    return TokenPair(access_token=access, refresh_token=refresh)


@auth_router.post("/refresh", response_model=TokenPair, summary="Exchange refresh for access")
async def refresh(body: RefreshRequest, request: Request, session: AsyncSession = Depends(get_session)) -> TokenPair:
    async with _pre_auth_scope(request, session, refresh_token=body.refresh_token):
        access, new_refresh = await _service(session).refresh(body.refresh_token)
    return TokenPair(access_token=access, refresh_token=new_refresh)


@auth_router.post("/logout", summary="Revoke the presented refresh token")
async def logout(body: RefreshRequest, request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    async with _pre_auth_scope(request, session, refresh_token=body.refresh_token):
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
    body: PasswordResetRequest, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    async with _pre_auth_scope(request, session, email=body.email):
        await _service(session).request_password_reset(body.email)
    # Always 200 — never reveal whether the email is registered.
    return {"data": {"requested": True}}


@auth_router.post("/password-reset/confirm", summary="Set a new password using a reset token")
async def password_reset_confirm(
    body: PasswordResetConfirm, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    async with _pre_auth_scope(request, session, reset_token=body.token):
        await _service(session).confirm_password_reset(body.token, body.new_password)
    return {"data": {"reset": True}}


@me_router.get("/me", response_model=MeResponse, summary="Current principal, roles, permissions")
async def me(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    from app.modules.settings.nav_features import disabled_nav_map
    from app.modules.settings.service import setting_value

    # Feature flags the client uses to shape the nav. `recruitment` is the funnel master switch;
    # `nav:<route>` entries are the configurable sidebar (only disabled ones are sent — the client
    # treats any absent key as on). The API stays the enforcement layer regardless.
    features = {"recruitment": bool(await setting_value(session, "recruitment.enabled"))}
    features.update(await disabled_nav_map(session))

    return MeResponse(
        authenticated=True,
        user_id=principal.user_id,
        email=principal.email,
        person_id=principal.person_id,
        roles=principal.roles,
        permissions=principal.permissions,
        features=features,
    )
