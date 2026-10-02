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
async def _pre_auth_scope(request: Request):
    """T1 — sign-in runs before we know the user's tenant, and RLS is fail-closed.

    On a tenant subdomain (production: icr.<base-domain>) the lookup is scoped to that tenant,
    so an email from another tenant is simply "not found". On a bare host (dev localhost) there
    is no tenant to scope to, so this one lookup uses the explicit owner bypass — which the
    restricted app role (pgr_app) cannot use, so with pgr_app sign in through a subdomain."""
    from app.core.tenant_context import set_current_tenant, system_scope
    from app.core.tenant_resolver import resolve_tenant_id_for_host

    host_tid = await resolve_tenant_id_for_host(request.headers.get("host", ""))
    if host_tid is not None:
        set_current_tenant(host_tid)
        yield
    else:
        async with system_scope():
            yield


@auth_router.post("/login", response_model=TokenPair, summary="Password grant")
async def login(body: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)) -> TokenPair:
    async with _pre_auth_scope(request):
        access, refresh, _ = await _service(session).authenticate(body.email, body.password)
    return TokenPair(access_token=access, refresh_token=refresh)


@auth_router.post("/refresh", response_model=TokenPair, summary="Exchange refresh for access")
async def refresh(body: RefreshRequest, request: Request, session: AsyncSession = Depends(get_session)) -> TokenPair:
    async with _pre_auth_scope(request):
        access, new_refresh = await _service(session).refresh(body.refresh_token)
    return TokenPair(access_token=access, refresh_token=new_refresh)


@auth_router.post("/logout", summary="Revoke the presented refresh token")
async def logout(body: RefreshRequest, request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    async with _pre_auth_scope(request):
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
    async with _pre_auth_scope(request):
        await _service(session).request_password_reset(body.email)
    # Always 200 — never reveal whether the email is registered.
    return {"data": {"requested": True}}


@auth_router.post("/password-reset/confirm", summary="Set a new password using a reset token")
async def password_reset_confirm(
    body: PasswordResetConfirm, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    async with _pre_auth_scope(request):
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
