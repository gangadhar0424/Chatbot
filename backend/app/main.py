"""FastAPI app for the intake chatbot — Milestone 2.

POST /chat now runs the real Prompt A intake turn: it loads the session's spec
+ history, calls the LLM once (in JSON mode) with Prompt A as the system prompt,
parses the {updated_spec, reply_to_user, phase} contract, merges the spec
forward, persists, and returns the user-facing reply.

Spec is persisted per session in memory (app.sessions). To make extraction
verifiable, the full spec is printed to the server console every turn and is
also available at GET /debug/spec/{session_id}.
"""

import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app import flow, sessions
from app.llm.provider import generate
from app.prompts import build_prompt_a_system_prompt
from app.schemas import ChatRequest, ChatResponse, Message

load_dotenv()

# Built once: Prompt A (verbatim) + the injected shared spec schema.
PROMPT_A_SYSTEM_PROMPT = build_prompt_a_system_prompt()

app = FastAPI(title="Project-intake chatbot", version="0.2.0")

# Allow the Next.js dev server to call us. Configurable for other origins.
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


def _build_turn_messages(spec: dict, history: list[Message], user_message: str) -> list[Message]:
    """Assemble the messages for one Prompt A call.

    Prompt A expects current_spec, the conversation history, and the latest
    user message. The spec is handed to the model as a leading user-role
    context message (Ollama's chat API has no separate context channel), then
    the real history, then this turn's message.
    """
    spec_context = Message(
        role="user",
        content=f"current_spec:\n{json.dumps(spec, indent=2)}",
    )
    new_turn = Message(role="user", content=user_message)
    return [spec_context, *history, new_turn]


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    session = sessions.get_or_create(req.session_id)

    messages = _build_turn_messages(session.spec, session.history, req.message)
    raw = await generate(
        messages,
        PROMPT_A_SYSTEM_PROMPT,
        format="json",
        temperature=0.3,
    )

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        # JSON mode should prevent this, but fail loudly rather than corrupting
        # the session if the model ever returns non-JSON.
        raise HTTPException(
            status_code=502,
            detail=f"Model did not return valid JSON: {exc}",
        ) from exc

    reply = parsed.get("reply_to_user", "")

    # Backend owns flow control, not the model. process_turn merges the model's
    # extraction, rejects sentinels fabricated for future sections, applies the
    # deterministic skip, normalizes structured-field + sentinel shapes, and
    # recomputes the authoritative _meta. phase flips to ready_for_prd only when
    # WE confirm every field is filled — never on the model's say-so.
    session.spec = flow.process_turn(
        session.spec, parsed.get("updated_spec"), req.message
    )
    phase = session.spec["_meta"]["phase"]

    # Append both sides of this turn to the authoritative history.
    session.history.append(Message(role="user", content=req.message))
    session.history.append(Message(role="assistant", content=reply))

    # Debug visibility: dump the full spec plus the backend-computed flow state
    # to the server console every turn.
    meta = session.spec["_meta"]
    print(f"\n=== spec after turn (session {req.session_id}) ===")
    print(json.dumps(session.spec, indent=2))
    print(
        f"[flow] section={meta['current_section']} "
        f"phase={phase} "
        f"completed={meta['completed_sections']} "
        f"missing={flow.missing_fields(session.spec)}"
    )
    print("=== end spec ===\n", flush=True)

    return ChatResponse(reply=reply, phase=phase, spec=session.spec)


@app.get("/debug/spec/{session_id}")
async def debug_spec(session_id: str):
    """Return the current spec JSON for a session — for verifying extraction."""
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="No such session")
    return {"session_id": session_id, "spec": session.spec}
