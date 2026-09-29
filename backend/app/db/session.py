"""`get_session` FastAPI dependency (arch §6.5)."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AppSessionFactory, ReadSessionFactory
from app.core.tenant_context import get_current_tenant


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
    """Read-only session routed to the read replica when configured (arch §13.1, §16).

    MT tenancy fix: this is a SEPARATE connection from the one `get_current_principal` sets
    the tenant on, so without this it would run with an unset `app.current_tenant` and RLS
    would fall open (return every tenant's rows). We stamp the tenant onto this connection
    when its transaction begins — that fires at query time, by which point the request's
    permission dependency has resolved and the tenant ContextVar is set.
    """
    async with ReadSessionFactory() as session:

        @event.listens_for(session.sync_session, "after_begin")
        def _apply_tenant(_sess, _trans, connection):  # noqa: ANN001 (sync SA event)
            tid = get_current_tenant()
            if tid is not None and connection.dialect.name == "postgresql":
                connection.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)").bindparams(t=str(tid))
                )

        yield session
