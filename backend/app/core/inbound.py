"""T4 — requests that arrive without a user token (partner webhooks, email-provider bounces).

They carry no token naming an institution, and row-level security is fail-closed, so each one
must establish its institution before touching the database, or it silently finds nothing and
can't write. The institution comes from, in order:

* the webhook address, ``/webhooks/<institution>/<system>`` (the single-address SaaS setup);
* the host, ``icr.<base-domain>`` (a subdomain deployment);
* otherwise the default deployment (a single-institution install).

If the address and the host both name an institution, they must agree.

Each institution has its own webhook secret, derived from the app secret, so a partner holding
institution A's secret can't post into institution B by changing the host. The default
deployment keeps the app secret itself, so existing single-tenant integrations keep working.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid

from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AuthError, NotFoundError, PermissionError
from app.core.tenant_context import DEFAULT_TENANT_ID, set_current_tenant
from app.core.tenant_resolver import tenant_for_request, tenant_id_for_subdomain


def webhook_secret(tenant_id: uuid.UUID) -> bytes:
    key = get_settings().app_secret_key.encode()
    if tenant_id == DEFAULT_TENANT_ID:
        return key
    return hmac.new(key, f"webhook:{tenant_id}".encode(), hashlib.sha256).hexdigest().encode()


def sign(tenant_id: uuid.UUID, raw: bytes) -> str:
    return hmac.new(webhook_secret(tenant_id), raw, hashlib.sha256).hexdigest()


async def inbound_tenant(request: Request, institution: str | None = None) -> uuid.UUID:
    """The institution an unauthenticated request is for, published as the acting tenant."""
    host_tid = await tenant_for_request(request)
    path_tid = None
    if institution is not None:
        path_tid = await tenant_id_for_subdomain(institution)
        if path_tid is None:
            raise NotFoundError("Unknown institution")
    if host_tid is not None and path_tid is not None and host_tid != path_tid:
        raise PermissionError("The address and the host name different institutions")
    tid = path_tid or host_tid or DEFAULT_TENANT_ID
    set_current_tenant(tid)
    return tid


async def verified_inbound(request: Request, institution: str | None = None) -> tuple[uuid.UUID, bytes]:
    """Resolve the institution and check ``X-Signature`` (HMAC-SHA256 of the raw body) against
    that institution's secret. Returns (tenant id, raw body)."""
    tid = await inbound_tenant(request, institution)
    raw = await request.body()
    if not hmac.compare_digest(sign(tid, raw), request.headers.get("X-Signature", "")):
        raise AuthError("Invalid webhook signature")
    return tid, raw
