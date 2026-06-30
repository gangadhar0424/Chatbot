"""Async SQLAlchemy engine and request-scoped session dependency.

DATABASE_URL is read from the environment (standard postgresql:// scheme).
Two libpq-only query params are stripped before the URL reaches asyncpg:
  - sslmode         asyncpg takes ssl config via connect_args, not the URL
  - channel_binding asyncpg implements SCRAM CB implicitly when SSL is active

_ssl_connect_arg() converts the sslmode value to the asyncpg connect_args
form so the same encryption intent is preserved.

pool_pre_ping=True detects stale connections after a Neon cold-start: the
pre-ping SELECT 1 fails on a dead connection, the engine discards it and
opens a fresh one. asyncpg's default connect timeout is 60 s; Neon wakes in
1-5 s, so the new connection succeeds and the slow first request shows up as
latency rather than an error.
"""

import os
import re

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

load_dotenv()


def _async_url(raw: str) -> str:
    """Rewrite postgres(ql):// to postgresql+asyncpg:// and strip libpq params."""
    url = re.sub(r"^postgres(ql)?://", "postgresql+asyncpg://", raw)
    url = re.sub(r"[?&]sslmode=[^&]*", "", url)
    url = re.sub(r"[?&]channel_binding=[^&]*", "", url)
    url = re.sub(r"\?&", "?", url)   # fix ?& left when sslmode was first param
    url = re.sub(r"[?&]$", "", url)  # trailing separator
    return url


def _ssl_connect_arg(raw: str) -> dict:
    """Map sslmode in the raw URL to asyncpg's connect_args ssl parameter."""
    m = re.search(r"[?&]sslmode=([^&]+)", raw)
    if not m:
        return {}
    mode = m.group(1).lower()
    return {
        "require": {"ssl": "require"},
        "verify-ca": {"ssl": True},
        "verify-full": {"ssl": True},
    }.get(mode, {})


_raw_url = os.getenv("DATABASE_URL")
if not _raw_url:
    raise RuntimeError("DATABASE_URL environment variable is not set")

engine = create_async_engine(
    _async_url(_raw_url),
    connect_args=_ssl_connect_arg(_raw_url),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI dependency: one AsyncSession per request, auto-closed after."""
    async with AsyncSessionLocal() as db:
        yield db
