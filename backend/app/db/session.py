"""`get_session` FastAPI dependency (arch §6.5)."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import ReadSessionFactory, SessionFactory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_read_session() -> AsyncGenerator[AsyncSession, None]:
    """Read-only session routed to the read replica when configured (arch §13.1, §16)."""
    async with ReadSessionFactory() as session:
        yield session
