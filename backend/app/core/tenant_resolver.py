"""MT-5 — resolve the acting tenant from the request Host (subdomain).

Maps `icr.pgr.example.com` (or `icr.localhost:3000`) to a tenant id, so the URL — not just
the JWT — establishes which tenant's space a request is in. This is defence in depth: an
authenticated user's token tenant is cross-checked against the host tenant, so a token for
tenant A cannot be replayed against tenant B's subdomain.

Design:
* Neutral hosts (bare apex, `www`, `localhost`, an IP, the dev host) resolve to None, which
  means "no specific tenant" — the caller then falls back to the JWT tenant. This keeps
  single-tenant and local/dev operation unchanged.
* Subdomain -> tenant_id is served from a small in-process cache (active tenants only),
  refreshed on a short TTL and on a miss, so there is no per-request DB hit in the hot path.
* Failures are swallowed to None — tenant resolution must never take the API down.
"""
from __future__ import annotations

import asyncio
import time
import uuid

# Hosts / first labels that never denote a tenant.
_NEUTRAL = {"", "www", "app", "api", "default", "localhost", "127", "0", "test", "testserver"}

_TTL_SECONDS = 60.0
_cache: dict[str, uuid.UUID] = {}
_loaded_at: float = 0.0
_lock = asyncio.Lock()


def subdomain_of(host: str, base_domain: str | None = None) -> str | None:
    """Tenant subdomain label for a host, or None (apex / neutral / not ours).

    With a configured ``base_domain`` (production), the tenant is the label directly in
    front of it: ``icr.pgr.icr.ac.uk`` -> ``icr``; the bare ``pgr.icr.ac.uk`` is the apex
    (None); a host not under the base domain is None. Without a base domain (dev), only
    ``<sub>.localhost`` is resolved, so an apex like ``pgr.example.com`` is never mistaken
    for the subdomain ``pgr``.
    """
    host = (host or "").split(":")[0].strip().lower()
    if not host:
        return None
    # An IPv4 literal is not a subdomain.
    if all(p.isdigit() for p in host.split(".")) and host.count(".") == 3:
        return None

    base = (base_domain or "").strip().lower().strip(".")
    if base:
        if host == base or not host.endswith("." + base):
            return None  # the apex itself, or a host outside our domain
        prefix = host[: -(len(base) + 1)]
        first = prefix.split(".")[0]
    elif host.endswith(".localhost") and host != "localhost":
        first = host.split(".")[0]
    else:
        return None
    return first if first not in _NEUTRAL else None


async def _reload() -> None:
    global _cache, _loaded_at
    from sqlalchemy import select

    from app.core.database import ReadSessionFactory
    from app.modules.tenant.models import Tenant

    async with ReadSessionFactory() as session:
        rows = (await session.execute(
            select(Tenant).where(
                Tenant.activated_at.is_not(None), Tenant.deactivated_at.is_(None)
            )
        )).scalars().all()
    _cache = {t.subdomain.strip().lower(): t.id for t in rows if t.subdomain}
    _loaded_at = time.monotonic()


async def resolve_tenant_id_for_host(host: str) -> uuid.UUID | None:
    """Tenant id for this Host, or None for neutral/unknown hosts (caller falls back)."""
    from app.core.config import get_settings

    sub = subdomain_of(host, get_settings().tenant_base_domain)
    if sub is None:
        return None
    try:
        if not _cache or (time.monotonic() - _loaded_at) > _TTL_SECONDS:
            async with _lock:
                if not _cache or (time.monotonic() - _loaded_at) > _TTL_SECONDS:
                    await _reload()
        tid = _cache.get(sub)
        if tid is None:  # unknown subdomain — one forced refresh in case a tenant is new
            async with _lock:
                await _reload()
            tid = _cache.get(sub)
        return tid
    except Exception:  # resolution must never break the request path
        return None


def _reset_cache_for_tests() -> None:
    global _cache, _loaded_at
    _cache, _loaded_at = {}, 0.0
