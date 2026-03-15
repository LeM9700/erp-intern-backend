import os
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import asyncio

# Import Base and all models
from app.db.base import Base
from app.models.user import User  # noqa: F401
from app.models.attendance import AttendanceSession  # noqa: F401
from app.models.task import Task, TaskProof, TaskReview  # noqa: F401
from app.models.file import File  # noqa: F401
from app.models.activity import ActivityLog  # noqa: F401
from app.models.notification import Notification  # noqa: F401

config = context.config

# Override sqlalchemy.url with DATABASE_URL from environment
database_url = os.getenv("DATABASE_URL", "")
# Railway injects postgresql://, Alembic async requiert postgresql+asyncpg://
if database_url and database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)  # pass URL to Alembic


if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
