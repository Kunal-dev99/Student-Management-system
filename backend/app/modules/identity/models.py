"""Identity ORM models: users, roles, permissions + join tables (arch §8.3, §12.2).

Portable across SQLite (dev) and PostgreSQL (prod) per decision D-04 — no dialect-specific
column types here.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

role_permission = Table(
    "role_permission",
    Base.metadata,
    Column("role_id", ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permission.id", ondelete="CASCADE"), primary_key=True),
)

user_role = Table(
    "user_role",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("role.id", ondelete="CASCADE"), primary_key=True),
)


class Permission(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "permission"
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)  # e.g. person.read
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Role(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "role"
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permission, lazy="selectin"
    )


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Phase 4A.4 — brute-force lockout.
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    roles: Mapped[list[Role]] = relationship(secondary=user_role, lazy="selectin")


class RefreshToken(UUIDMixin, Base):
    """One row per issued refresh token (keyed by the JWT `jti`) so logout/rotation can revoke it.

    The token itself stays a signed JWT; this table is the revocation list (arch §12.1 hardening).
    """
    __tablename__ = "refresh_token"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    jti: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PasswordResetToken(UUIDMixin, Base):
    """Single-use, time-boxed password-reset token. Only the hash is stored (arch §12.1)."""
    __tablename__ = "password_reset_token"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
