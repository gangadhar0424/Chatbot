"""In-memory per-session store for the intake chatbot.

Milestone 2 scope: hold each session's spec JSON and conversation history in a
process-local dict, keyed by session_id. This is deliberately ephemeral — a
restart loses everything. Redis/Postgres-backed persistence arrives in
Milestone 5 behind this same get/save shape.
"""

from typing import Any

from app.schemas import Message
from app.spec import initial_spec


class Session:
    """One user's intake state: the spec so far plus the full message history."""

    def __init__(self) -> None:
        self.spec: dict[str, Any] = initial_spec()
        self.history: list[Message] = []


_SESSIONS: dict[str, Session] = {}


def get_or_create(session_id: str) -> Session:
    """Return the existing session for this id, creating a fresh one if needed."""
    session = _SESSIONS.get(session_id)
    if session is None:
        session = Session()
        _SESSIONS[session_id] = session
    return session


def get(session_id: str) -> Session | None:
    """Return the session for this id, or None if it doesn't exist."""
    return _SESSIONS.get(session_id)
