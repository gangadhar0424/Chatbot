import asyncio
import os
import sys
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Ensure the backend package is importable when alembic runs from backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv()

from app.db import Base, _async_url, _ssl_connect_arg  # noqa: E402
import app.models  # noqa: F401, E402 — registers SessionRow + GroundingLogRow with Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_raw_url() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        raise RuntimeError("DATABASE_URL is not set")
    return raw


def run_migrations_offline() -> None:
    context.configure(
        url=_async_url(_get_raw_url()),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    raw = _get_raw_url()
    connectable = create_async_engine(
        _async_url(raw),
        connect_args=_ssl_connect_arg(raw),
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
