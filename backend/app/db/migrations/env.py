"""Alembic environment — async, driven by app settings (arch §8.15)."""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from app.core.config import get_settings
from app.db.base import Base

# Import module models so Alembic autogenerate sees every table.
from app.modules.identity import models as identity_models  # noqa: F401,E402
from app.modules.person import models as person_models  # noqa: F401,E402
from app.modules.student_record import models as student_models  # noqa: F401,E402
from app.modules.taught import models as taught_models  # noqa: F401,E402
from app.modules.recruitment import models as recruitment_models  # noqa: F401,E402
from app.modules.recruitment import f3_models as recruitment_f3_models  # noqa: F401,E402
from app.modules.admissions import models as admissions_models  # noqa: F401,E402
from app.modules.supervision import models as supervision_models  # noqa: F401,E402
from app.modules.progression import models as progression_models  # noqa: F401,E402
from app.modules.settings import models as settings_models  # noqa: F401,E402
from app.modules.pattern_lab import models as pattern_lab_models  # noqa: F401,E402
from app.modules.funding import models as funding_models  # noqa: F401,E402
from app.modules.thesis import models as thesis_models  # noqa: F401,E402
from app.modules.completion import models as completion_models  # noqa: F401,E402
from app.modules.workflow import models as workflow_models  # noqa: F401,E402
from app.modules.integration import models as integration_models  # noqa: F401,E402
from app.modules.exports import models as exports_models  # noqa: F401,E402
from app.modules.documents import models as documents_models  # noqa: F401,E402
from app.modules.notifications import models as notifications_models  # noqa: F401,E402
from app.modules.audit import models as audit_models  # noqa: F401,E402
from app.modules.research import models as research_models  # noqa: F401,E402
from app.modules.assistant import f6_models as assistant_f6_models  # noqa: F401,E402
from app.modules.assistant import telemetry_models as assistant_telemetry_models  # noqa: F401,E402
from app.modules.icr import models as icr_models  # noqa: F401,E402
from app.modules.supervision import w2_models as supervision_w2_models  # noqa: F401,E402

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _changes_schema() -> bool:
    """True for commands that can change the schema (upgrade/downgrade, or a programmatic call).
    Read-only commands such as `alembic current` or `history` leave the reporting views alone."""
    cmd = getattr(getattr(config, "cmd_opts", None), "cmd", None)
    name = getattr(cmd[0], "__name__", "") if cmd else ""
    return name in ("", "upgrade", "downgrade")


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        if connection.dialect.name == "postgresql":
            # T1 — RLS is fail-closed; migrations (backfills, checks) work across every tenant,
            # so this connection opts in to the owner's explicit bypass for its whole session.
            connection.exec_driver_sql("SELECT set_config('app.bypass_tenant', 'on', false)")
        if connection.dialect.name == "postgresql" and _changes_schema():
            # T3 — the per-institution reporting views depend on core columns, and Postgres won't
            # alter a column a view uses. Drop them first, rebuild them from the catalogue after.
            from app.db import tenant_views
            tenant_views.drop_all(connection)
            context.run_migrations()
            built = tenant_views.rebuild(connection)
            if built:
                print(f"tenant views rebuilt: {built}")
        else:
            context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
