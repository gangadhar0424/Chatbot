"""Pydantic request/response models for the chat endpoint.

Milestone 2: each turn is keyed by session_id. The backend owns the
authoritative spec + history per session, so the client only needs to send its
id and the new message. The response carries the user-facing reply plus the
phase flag (and the current spec, for convenience/debugging).

Milestone 9: session_id is constrained to alphanumeric + hyphens + underscores
(max 128 chars) to prevent path-traversal and injection via that field.
message is capped at 16 384 chars (~4 k tokens) to limit DoS via oversized input.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# Shared validator args — applied to every request type that carries session_id.
_SID_FIELD = Field(max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    session_id: str = _SID_FIELD
    message: str = Field(max_length=16_384)
    # Kept for backward compatibility with the Milestone 1 client; the backend
    # now relies on its own stored history and ignores this.
    history: list[Message] = []


class ChatResponse(BaseModel):
    reply: str
    phase: Literal["gathering", "ready_for_prd"]
    spec: dict[str, Any]


class PrdRequest(BaseModel):
    session_id: str = _SID_FIELD


class PrdResponse(BaseModel):
    prd: str


class ScaffoldRequest(BaseModel):
    session_id: str = _SID_FIELD


class ScaffoldResponse(BaseModel):
    output_path: str
    template: str
    match_exact: bool
    match_note: str | None
    files_created: list[str]
