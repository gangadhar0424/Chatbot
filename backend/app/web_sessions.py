"""Sync, owner-aware per-session store backing prd_routes.py.

Same Session(spec, history) shape as app/sessions.py, but reads/writes the
new IntakeSession model (SQLite, owner column) instead of the Postgres
SessionRow. app/sessions.py is untouched and keeps serving the old app.
"""

from typing import Any

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session as OrmSession

from app.schemas import Message
from app.spec import initial_spec
from app.web_models import IntakeSession


class Session:
    """One user's intake state: the running spec plus the full message history."""

    def __init__(self, spec: dict[str, Any], history: list[Message]) -> None:
        self.spec = spec
        self.history = history


def _row_to_session(row: IntakeSession) -> Session:
    history = [Message(**m) for m in (row.history_json or [])]
    return Session(spec=dict(row.spec_json), history=history)


def get_or_create(db: OrmSession, session_id: str, owner: str) -> Session:
    """Return the existing session for this id (if owned by `owner`), or a blank one.

    The blank session is not written here — save() does that at the end of
    the request so an errored turn never persists a partial session.
    """
    row = db.get(IntakeSession, session_id)
    if row is None or row.owner not in (None, owner):
        return Session(spec=initial_spec(), history=[])
    return _row_to_session(row)


def get(db: OrmSession, session_id: str, owner: str) -> Session | None:
    """Return the session for this id, or None if it doesn't exist or isn't owned by `owner`."""
    row = db.get(IntakeSession, session_id)
    if row is None or row.owner not in (None, owner):
        return None
    return _row_to_session(row)


def save(db: OrmSession, session_id: str, owner: str, session: Session) -> None:
    """Upsert spec and history, scoped to owner, and commit."""
    history_data = [{"role": m.role, "content": m.content} for m in session.history]
    stmt = (
        sqlite_insert(IntakeSession)
        .values(
            session_id=session_id,
            owner=owner,
            spec_json=session.spec,
            history_json=history_data,
        )
        .on_conflict_do_update(
            index_elements=["session_id"],
            set_={
                "owner": owner,
                "spec_json": session.spec,
                "history_json": history_data,
            },
        )
    )
    db.execute(stmt)
    db.commit()
