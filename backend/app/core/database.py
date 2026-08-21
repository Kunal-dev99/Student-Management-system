"""Async engine and session factory (arch §4, §6.5)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_settings = get_settings()

# Per-worker pool. Production runs multiple uvicorn/gunicorn workers behind a balancer
# (arch §16), each with its own pool, fronted by PgBouncer — so the pool is sized per process,
# not per fleet (N_workers * (pool_size+max_overflow) must stay under Postgres max_connections).
# SQLite ignores pool sizing.
_POOL = {} if _settings.database_url.startswith("sqlite") else {"pool_size": 10, "max_overflow": 5}

engine: AsyncEngine = create_async_engine(
    _settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
    **_POOL,
)

SessionFactory = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

# Read path (arch §13.1, §16): reporting/analytics reads route to a read replica when one is
# configured (DATABASE_REPLICA_URL), keeping heavy reads off the write primary. Falls back to
# the primary when no replica is set.
read_engine: AsyncEngine = (
    create_async_engine(_settings.database_replica_url, echo=False, future=True, pool_pre_ping=True, **_POOL)
    if _settings.database_replica_url
    else engine
)

ReadSessionFactory = async_sessionmaker(
    bind=read_engine, class_=AsyncSession, expire_on_commit=False
)

USING_REPLICA = bool(_settings.database_replica_url)
