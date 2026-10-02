"""Per-request tenant context (MT-2).

A dependency-free home for "which tenant is this request acting as", so both the ORM
(insert-time stamping via ``TenantMixin``) and the Postgres session variable used by RLS
read from one place. Deliberately imports nothing from the model or app layers to avoid
circular imports — ``app.db.base`` imports this.

The context is a ``ContextVar`` so it is safe under async concurrency: each request/task
gets its own value. It is set in the request lifecycle (see ``core.dependencies``) and in
scripts/seeds that want to act as a specific tenant.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

# The single-tenant deployment everything is backfilled to until per-tenant onboarding.
# Mirrors app.modules.tenant.models.DEFAULT_TENANT_ID (kept in sync; same literal).
DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

_current_tenant: ContextVar[uuid.UUID | None] = ContextVar("current_tenant", default=None)


def set_current_tenant(tenant_id: uuid.UUID | None) -> None:
    """Set the acting tenant for the current context (request/task)."""
    _current_tenant.set(tenant_id)


def get_current_tenant() -> uuid.UUID | None:
    """The acting tenant, or None if unset (e.g. an unauthenticated context)."""
    return _current_tenant.get()


# T1 — explicit cross-tenant bypass. Postgres RLS is fail-closed: with no tenant set, a query
# sees no rows. Code that genuinely works across tenants (migrations, seeds, the worker's
# tenant loop, the dev login lookup on a bare host) opts in here, and only the database owner
# role honours it — the app role (pgr_app) and reporting roles never can.
_bypass: ContextVar[bool] = ContextVar("tenant_bypass", default=False)


def is_tenant_bypass() -> bool:
    return _bypass.get()


class system_scope:
    """``with system_scope():`` / ``async with system_scope():`` — run cross-tenant code.

    Keep it as narrow as possible: wrap the one lookup or the tool's entry point, never a
    whole request. Every session started inside it sets ``app.bypass_tenant`` for its
    transaction (see ``core.database``)."""

    def __enter__(self):
        self._token = _bypass.set(True)
        return self

    def __exit__(self, *exc):
        _bypass.reset(self._token)
        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *exc):
        return self.__exit__(*exc)


class tenant_scope:
    """``async with tenant_scope(tid):`` — act as one tenant (e.g. the worker's per-tenant loop).
    Restores the previous tenant on exit."""

    def __init__(self, tenant_id: uuid.UUID | None) -> None:
        self.tenant_id = tenant_id

    def __enter__(self):
        self._token = _current_tenant.set(self.tenant_id)
        return self

    def __exit__(self, *exc):
        _current_tenant.reset(self._token)
        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *exc):
        return self.__exit__(*exc)


def resolve_tenant_for_write() -> uuid.UUID:
    """Tenant to stamp on a new row: the acting tenant, or the default deployment.

    Never returns None — a row must belong to a tenant. Falling back to the default keeps
    seeds, migrations and single-tenant operation working with no behaviour change.
    """
    return _current_tenant.get() or DEFAULT_TENANT_ID
