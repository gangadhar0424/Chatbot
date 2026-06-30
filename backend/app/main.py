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
from app.prompts import build_prompt_a_system_prompt, build_prompt_b_system_prompt
from app.schemas import ChatRequest, ChatResponse, Message, PrdRequest, PrdResponse

load_dotenv()

# Built once at startup.
PROMPT_A_SYSTEM_PROMPT = build_prompt_a_system_prompt()
PROMPT_B_SYSTEM_PROMPT = build_prompt_b_system_prompt()

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


def _strip_md_fence(text: str) -> str:
    """Remove a wrapping ```markdown / ``` fence that small local models add
    despite being told not to. Leaves the content untouched if no fence is present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _prepare_spec_for_prd(spec: dict) -> str:
    """Restructure the spec into a pre-grouped user message for Prompt B.

    The 3B model reliably transcribes already-sorted data but struggles to
    re-derive groupings from a flat list — the same class of problem M3 solved
    by having the backend own _meta rather than trusting the model. Here we:

      - Split mvp_features into P0/P1/P2 keys so the model transcribes each
        bucket directly into the right subsection.
      - Extract future_features entirely from the JSON and render them as a
        named bullet list in the preamble text, so the model can't confuse
        them with a low-priority MVP tier.
      - Split known_risks into High/Medium/Low keys for ordered transcription.
      - Strip _meta — it's internal bookkeeping Prompt B doesn't need.

    Returns a string (not a dict) so the preamble instruction travels with the
    data in the same user message.
    """
    import copy

    out = copy.deepcopy(spec)
    out.pop("_meta", None)

    # --- Collect sentinel fields BEFORE restructuring -----------------------
    # Restructuring pops mvp_features and known_risks, so we must scan first.
    _FIELD_LABELS: dict[str, dict[str, str]] = {
        "problem_and_vision": {
            "one_liner": "One-liner summary",
            "problem_statement": "Problem statement",
            "business_goals": "Business goals",
            "motivation": "Motivation",
            "success_metrics": "Success metrics",
        },
        "users_and_use_cases": {
            "target_users": "Target users",
            "primary_use_cases": "Primary use cases",
            "user_personas": "User personas",
        },
        "scope_and_features": {
            "mvp_features": "MVP features",
            "future_features": "Future features (post-MVP)",
            "explicitly_out_of_scope": "Explicitly out of scope",
        },
        "technical_requirements": {
            "tech_stack_preference": "Tech stack preference",
            "integrations": "Integrations",
            "data_model": "Data model",
            "non_functional_requirements": "Non-functional requirements",
            "compliance_requirements": "Compliance requirements",
        },
        "ux_design": {
            "platform": "Platform",
            "design_preferences": "Design preferences",
            "accessibility_needs": "Accessibility needs",
        },
        "deployment_infra": {
            "deployment_target": "Deployment target",
            "environments": "Environments",
            "cicd_needs": "CI/CD needs",
        },
        "timeline_resources": {
            "timeline": "Timeline",
            "budget": "Budget",
            "team_size_roles": "Team size and roles",
        },
        "maintenance_ops": {
            "maintenance_plan": "Maintenance plan",
            "monitoring_logging": "Monitoring and logging",
            "support_plan": "Support plan",
        },
        "risks_assumptions": {
            "known_risks": "Known risks",
            "assumptions": "Assumptions",
            "dependencies": "Dependencies",
        },
    }
    unspecified_fields: list[str] = []
    for _section, _fields in _FIELD_LABELS.items():
        _sec = out.get(_section, {})
        for _field, _label in _fields.items():
            _val = _sec.get(_field)
            if _val == "unspecified" or _val == ["unspecified"]:
                unspecified_fields.append(_label)

    # --- scope_and_features -------------------------------------------------
    scope = out.get("scope_and_features", {})

    # Pre-group mvp_features by priority.
    raw_features = scope.pop("mvp_features", [])
    if isinstance(raw_features, list) and raw_features not in ([], ["unspecified"]):
        scope["mvp_features_must_have_P0"] = [
            f["name"] for f in raw_features
            if isinstance(f, dict) and f.get("priority") == "P0"
        ]
        scope["mvp_features_should_have_P1"] = [
            f["name"] for f in raw_features
            if isinstance(f, dict) and f.get("priority") == "P1"
        ]
        scope["mvp_features_could_have_P2"] = [
            f["name"] for f in raw_features
            if isinstance(f, dict) and f.get("priority") == "P2"
        ]
    else:
        scope["mvp_features_must_have_P0"] = raw_features
        scope["mvp_features_should_have_P1"] = []
        scope["mvp_features_could_have_P2"] = []

    # Pull future_features out of the JSON entirely and render them as explicit
    # text in the preamble so the model doesn't have to discover or place them.
    raw_future = scope.pop("future_features", [])
    if isinstance(raw_future, list) and raw_future not in ([], ["unspecified"]):
        future_block = "\n".join(f"  - {f}" for f in raw_future)
    else:
        future_block = "  (none specified)"

    # --- risks_assumptions: pre-group known_risks by impact -----------------
    risks = out.get("risks_assumptions", {})
    raw_risks = risks.pop("known_risks", [])
    if isinstance(raw_risks, list) and raw_risks not in ([], ["unspecified"]):
        for impact in ("High", "Medium", "Low"):
            risks[f"known_risks_{impact.lower()}_impact"] = [
                {"risk": r["risk"], "mitigation": r.get("mitigation", "unspecified")}
                for r in raw_risks
                if isinstance(r, dict) and r.get("impact") == impact
            ]
    else:
        risks["known_risks_high_impact"] = raw_risks
        risks["known_risks_medium_impact"] = []
        risks["known_risks_low_impact"] = []

    preamble = (
        "The specification below has been pre-processed. "
        "Transcribe these groupings directly into the PRD — do NOT re-sort or re-derive them.\n\n"
        "SCOPE SECTION — use exactly these subsections in this order:\n"
        "  1. Must-have (P0): transcribe mvp_features_must_have_P0 from the JSON\n"
        "  2. Should-have (P1): transcribe mvp_features_should_have_P1 from the JSON\n"
        "  3. Could-have (P2): transcribe mvp_features_could_have_P2 from the JSON\n"
        "  4. Future scope (post-MVP, not part of this release):\n"
        f"{future_block}\n"
        "  5. Explicitly out of scope: transcribe explicitly_out_of_scope from the JSON\n\n"
        "RISKS SECTION — transcribe known risks in this order:\n"
        "  High-impact: transcribe known_risks_high_impact from the JSON\n"
        "  Medium-impact: transcribe known_risks_medium_impact from the JSON\n"
        "  Low-impact: transcribe known_risks_low_impact from the JSON\n\n"
    )

    if unspecified_fields:
        oq_lines = "\n".join(f"  - {f}" for f in unspecified_fields)
        preamble += (
            "OPEN QUESTIONS SECTION (section 11) — the user explicitly skipped these\n"
            "fields. Copy this exact list, by name, under '## Open Questions / To Be\n"
            "Determined'. Do NOT list anything else there; do NOT move these items into\n"
            "other sections:\n"
            f"{oq_lines}\n\n"
        )
    else:
        preamble += (
            "OPEN QUESTIONS SECTION (section 11) — no fields were left unspecified;\n"
            "write a short note confirming all requirements are fully documented.\n\n"
        )

    return preamble + json.dumps(out, indent=2)


def _strip_trailing_commentary(text: str) -> str:
    """Strip a trailing plain-text paragraph models append after the final section.

    Prompt B says 'no commentary before or after the document' but small local
    models often add a closing summary anyway. We remove the last paragraph-block
    only when it contains zero markdown structural markers (headings, list items,
    fences, tables) — i.e. it's free-floating prose, not PRD content.
    """
    import re

    text = text.rstrip()
    # Split on blank lines to get paragraph blocks.
    blocks = re.split(r"\n[ \t]*\n", text)
    if len(blocks) < 2:
        return text
    last = blocks[-1].strip()
    # Any line starting with a markdown marker means this is real content.
    has_marker = re.search(r"(?m)^[ \t]*(?:#|-|\*|\d+\.|>|```|\|)", last)
    if not has_marker:
        return "\n\n".join(b for b in blocks[:-1] if b.strip())
    return text


@app.post("/generate-prd", response_model=PrdResponse)
async def generate_prd(req: PrdRequest) -> PrdResponse:
    """Generate the PRD from a completed spec using Prompt B.

    Runs the backend-side completeness gate before calling the model — if any
    field is still null or [] the spec isn't truly done and we return 409 rather
    than generating a partial document. Called once by the frontend after the
    user confirms their answers on the review screen.

    The spec is pre-processed by _prepare_spec_for_prd before being sent:
    mvp_features and known_risks are pre-grouped, and future_features are
    rendered as explicit preamble text so the model transcribes rather than
    re-derives. The result is fence-stripped and trailing commentary removed.
    """
    session = sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="No such session")

    missing = flow.missing_fields(session.spec)
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"Spec is not complete — missing fields: {missing}",
        )

    user_content = _prepare_spec_for_prd(session.spec)
    prd_text = await generate(
        [Message(role="user", content=user_content)],
        PROMPT_B_SYSTEM_PROMPT,
        temperature=0.6,
    )

    return PrdResponse(prd=_strip_trailing_commentary(_strip_md_fence(prd_text)))
