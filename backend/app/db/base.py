"""Declarative base with a consistent naming convention (arch §8.1).

Every persisted row carries created_at/updated_at (UTC). In PostgreSQL, updated_at is
maintained by a trigger installed in the first migration; the ORM default is a safety net.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.tenant_context import resolve_tenant_for_write

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TenantMixin:
    """Marks a table as tenant-owned (MT-2).

    ``tenant_id`` is **nullable during rollout** so the additive migration and existing
    single-tenant data keep working, but a Python-side ``default`` stamps every new row
    with the acting tenant (or the default deployment), so rows are never left unscoped.
    Row isolation itself is enforced in Postgres by RLS policies that read
    ``current_setting('app.current_tenant')`` — this column is what those policies match on.
    Indexed because every tenant-scoped query filters on it.
    """
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenant.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
        default=resolve_tenant_for_write,
    )


class TimestampMixin:
    # timestamptz (UTC) per arch §8.1 — timezone-aware on Postgres, portable to SQLite.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
