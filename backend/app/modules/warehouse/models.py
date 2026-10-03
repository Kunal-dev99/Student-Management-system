"""Data warehouse export: what is published, when, to whom, and what changed.

Every table is tenant-owned (RLS, fail-closed): an institution's publications, runs, consumers and
change log are its own. The published content itself is the T3 catalogue
(``app.db.tenant_views.CATALOGUE``), read as one institution at a time.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class WarehouseDeletedRow(UUIDMixin, TenantMixin, Base):
    """A row removed from a published table, written by a database trigger, so incremental
    extracts can tell the warehouse what to delete (the row itself is gone)."""
    __tablename__ = "warehouse_deleted_row"
    __table_args__ = (Index("ix_warehouse_deleted_row_lookup", "tenant_id", "table_name", "deleted_at"),)

    table_name: Mapped[str] = mapped_column(String(80))
    row_id: Mapped[uuid.UUID] = mapped_column()
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WarehousePublication(UUIDMixin, TenantMixin, TimestampMixin, Base):
    """A scheduled publish of catalogue objects to the institution's storage target."""
    __tablename__ = "warehouse_publication"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_warehouse_publication_tenant_name"),)

    name: Mapped[str] = mapped_column(String(120))
    objects: Mapped[list | None] = mapped_column(JSON, nullable=True)      # None = every object
    file_format: Mapped[str] = mapped_column(String(10), default="parquet")  # parquet | csv
    frequency: Mapped[str] = mapped_column(String(10), default="daily")     # daily | hourly
    run_at_hour: Mapped[int] = mapped_column(Integer, default=2)           # UTC hour, daily runs
    personal_data: Mapped[bool] = mapped_column(Boolean, default=False)
    # A full extract every N days catches anything incremental could miss (and lets a warehouse
    # rebuild from one run). 0 = never after the first.
    full_every_days: Mapped[int] = mapped_column(Integer, default=7)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_full_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class WarehouseRun(UUIDMixin, TenantMixin, Base):
    __tablename__ = "warehouse_run"

    publication_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouse_publication.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="running")    # running | succeeded | failed
    mode: Mapped[str] = mapped_column(String(12))                          # full | incremental
    triggered_by: Mapped[str] = mapped_column(String(12), default="schedule")  # schedule | manual
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str | None] = mapped_column(String(400), nullable=True)
    manifest: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class WarehouseWatermark(UUIDMixin, TenantMixin, Base):
    """How far each object of a publication has been published (its last window end)."""
    __tablename__ = "warehouse_watermark"
    __table_args__ = (UniqueConstraint("tenant_id", "publication_id", "object_name",
                                       name="uq_warehouse_watermark_tenant_publication_id_object_name"),)

    publication_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouse_publication.id", ondelete="CASCADE"), index=True)
    object_name: Mapped[str] = mapped_column(String(80))
    high_water: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WarehouseConsumer(UUIDMixin, TenantMixin, TimestampMixin, Base):
    """A system that pulls through the API with OAuth client credentials (e.g. a warehouse loader).
    Only the secret's hash is stored; the secret is shown once."""
    __tablename__ = "warehouse_consumer"

    name: Mapped[str] = mapped_column(String(120))
    # Random, so unique across institutions: it identifies the consumer before the institution is
    # known (the token request), like a referee token.
    client_id: Mapped[str] = mapped_column(String(64), unique=True)
    secret_hash: Mapped[str] = mapped_column(String(128))
    objects: Mapped[list | None] = mapped_column(JSON, nullable=True)      # None = every object
    personal_data: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
