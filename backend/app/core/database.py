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

# MT-6 — the API request path connects through the fail-closed, NON-OWNER app role when
# APP_DATABASE_URL is configured; otherwise it falls back to the owner engine (dev default,
# unchanged). The owner engine (`engine`/`SessionFactory`) is kept for migrations, seeds and
# the background worker, which run without a tenant context and must bypass RLS.
app_engine: AsyncEngine = (
    create_async_engine(
        _settings.app_database_url, echo=False, future=True, pool_pre_ping=True, **_POOL
    )
    if _settings.app_database_url
    else engine
)

AppSessionFactory = async_sessionmaker(
    bind=app_engine, class_=AsyncSession, expire_on_commit=False
)

USING_APP_ROLE = bool(_settings.app_database_url)


# T1 — every ORM session publishes the acting tenant (and any explicit cross-tenant bypass) to
# Postgres at the start of each transaction, transaction-local, so RLS sees it. This covers
# sessions a request opens itself (streaming AI features, audit/telemetry writes) as well as the
# request session — no code path has to remember to set it. RLS is fail-closed: no tenant and no
# bypass means no rows.
def _publish_tenant(session, transaction, connection) -> None:  # noqa: ANN001 (SA event)
    if connection.dialect.name != "postgresql":
        return
    from sqlalchemy import text as _text

    from app.core.tenant_context import get_current_tenant, is_tenant_bypass

    tid = get_current_tenant()
    connection.execute(
        _text("SELECT set_config('app.current_tenant', :t, true), set_config('app.bypass_tenant', :b, true)")
        .bindparams(t=str(tid) if tid is not None else "", b="on" if is_tenant_bypass() else "")
    )


from sqlalchemy import event as _event  # noqa: E402
from sqlalchemy.orm import Session as _Session  # noqa: E402

_event.listen(_Session, "after_begin", _publish_tenant)
