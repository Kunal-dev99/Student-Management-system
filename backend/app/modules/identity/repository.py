"""Data access for identity (queries only — arch §6.1)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import PasswordResetToken, RefreshToken, Role, User


class IdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- refresh token store (revocation list, arch §12.1) ---
    def add_refresh_token(self, user_id: uuid.UUID, jti: str, expires_at: datetime) -> None:
        self.session.add(RefreshToken(
            user_id=user_id, jti=jti, expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
        ))

    async def get_refresh_token(self, jti: str) -> RefreshToken | None:
        return (await self.session.execute(
            select(RefreshToken).where(RefreshToken.jti == jti)
        )).scalar_one_or_none()

    async def revoke_refresh_token(self, jti: str) -> None:
        await self.session.execute(
            update(RefreshToken).where(RefreshToken.jti == jti, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )

    async def revoke_all_refresh_tokens(self, user_id: uuid.UUID) -> int:
        res = await self.session.execute(
            update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        return res.rowcount or 0

    # --- password reset tokens ---
    def add_reset_token(self, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> None:
        self.session.add(PasswordResetToken(
            user_id=user_id, token_hash=token_hash, expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
        ))

    async def get_reset_token(self, token_hash: str) -> PasswordResetToken | None:
        return (await self.session.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )).scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> User | None:
        res = await self.session.execute(
            select(User).where(User.email == email.lower())
        )
        return res.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        res = await self.session.execute(select(User).where(User.id == user_id))
        return res.scalar_one_or_none()

    async def get_user_by_person(self, person_id: uuid.UUID) -> User | None:
        res = await self.session.execute(select(User).where(User.person_id == person_id))
        return res.scalars().first()

    async def get_role_by_name(self, name: str) -> Role | None:
        res = await self.session.execute(select(Role).where(Role.name == name))
        return res.scalar_one_or_none()
