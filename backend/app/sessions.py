"""Postgres-backed per-session store for the intake chatbot.

Each session's spec JSON and conversation history are stored as JSONB columns
in the 'sessions' table. An AsyncSession must be injected by the caller (via
FastAPI's Depends mechanism) so all DB work participates in the same
request-scoped connection.

The Session dataclass shape (spec + history) is unchanged from the previous
in-memory implementation — callers just await each function and supply db.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SessionRow
from app.schemas import Message
from app.spec import initial_spec


class Session:
    """One user's intake state: the running spec plus the full message history."""

    def __init__(self, spec: dict[str, Any], history: list[Message]) -> None:
        self.spec = spec
        self.history = history


def _row_to_session(row: SessionRow) -> Session:
    history = [Message(**m) for m in (row.history or [])]
    return Session(spec=dict(row.spec), history=history)


async def get_or_create(db: AsyncSession, session_id: str) -> Session:
    """Return the existing session for this id, or a blank one if none exists.

    The blank session is not written to the DB here — save() handles that at
    the end of the request so we never store a session that errored mid-turn.
    """
    result = await db.execute(
        select(SessionRow).where(SessionRow.session_id == session_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return Session(spec=initial_spec(), history=[])
    return _row_to_session(row)


async def get(db: AsyncSession, session_id: str) -> Session | None:
    """Return the session for this id, or None if it doesn't exist."""
    result = await db.execute(
        select(SessionRow).where(SessionRow.session_id == session_id)
    )
    row = result.scalar_one_or_none()
    return _row_to_session(row) if row is not None else None


async def save(db: AsyncSession, session_id: str, session: Session) -> None:
    """Upsert spec and history back to Postgres and commit."""
    history_data = [{"role": m.role, "content": m.content} for m in session.history]
    stmt = (
        pg_insert(SessionRow)
        .values(
            session_id=session_id,
            spec=session.spec,
            history=history_data,
        )
        .on_conflict_do_update(
            index_elements=["session_id"],
            set_={
                "spec": session.spec,
                "history": history_data,
                "updated_at": func.now(),
            },
        )
    )
    await db.execute(stmt)
    await db.commit()
