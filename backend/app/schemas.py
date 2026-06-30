"""Pydantic request/response models for the chat endpoint.

Milestone 2: each turn is keyed by session_id. The backend owns the
authoritative spec + history per session, so the client only needs to send its
id and the new message. The response carries the user-facing reply plus the
phase flag (and the current spec, for convenience/debugging).
"""

from typing import Any, Literal

from pydantic import BaseModel


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    # Kept for backward compatibility with the Milestone 1 client; the backend
    # now relies on its own stored history and ignores this.
    history: list[Message] = []


class ChatResponse(BaseModel):
    reply: str
    phase: Literal["gathering", "ready_for_prd"]
    spec: dict[str, Any]


class PrdRequest(BaseModel):
    session_id: str


class PrdResponse(BaseModel):
    prd: str
