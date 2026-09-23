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


def resolve_tenant_for_write() -> uuid.UUID:
    """Tenant to stamp on a new row: the acting tenant, or the default deployment.

    Never returns None — a row must belong to a tenant. Falling back to the default keeps
    seeds, migrations and single-tenant operation working with no behaviour change.
    """
    return _current_tenant.get() or DEFAULT_TENANT_ID
