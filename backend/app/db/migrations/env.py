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
from app.modules.recruitment import models as recruitment_models  # noqa: F401,E402
from app.modules.admissions import models as admissions_models  # noqa: F401,E402
from app.modules.supervision import models as supervision_models  # noqa: F401,E402
from app.modules.progression import models as progression_models  # noqa: F401,E402
from app.modules.funding import models as funding_models  # noqa: F401,E402
from app.modules.thesis import models as thesis_models  # noqa: F401,E402
from app.modules.completion import models as completion_models  # noqa: F401,E402
from app.modules.workflow import models as workflow_models  # noqa: F401,E402
from app.modules.integration import models as integration_models  # noqa: F401,E402
from app.modules.exports import models as exports_models  # noqa: F401,E402

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


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
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
