"""`get_session` FastAPI dependency (arch §6.5)."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AppSessionFactory, ReadSessionFactory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    # MT-6: the API request path uses the fail-closed app role when configured, else the
    # owner engine (AppSessionFactory falls back to it). Worker/seed keep SessionFactory.
    async with AppSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_read_session() -> AsyncGenerator[AsyncSession, None]:
    """Read-only session routed to the read replica when configured (arch §13.1, §16)."""
    async with ReadSessionFactory() as session:
        yield session
