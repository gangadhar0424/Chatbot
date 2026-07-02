"""PRD intake routes, shaped like ai-system's note_routes.py: a setup_*_routes()
function that builds and returns an APIRouter, rather than a bare FastAPI()
app with @app.post.

Reuses spec.py, flow.py, and prompts.py unchanged (the project's stated
framework-independent core). Persistence goes through web_sessions.py /
web_models.py (new SQLite-backed IntakeSession, owner-scoped) instead of the
Postgres-backed app/sessions.py that backend/app/main.py still uses — that
module and backend/app/main.py are untouched.

The PRD pre/post-processing helpers below (_strip_md_fence,
_prepare_spec_for_prd, _strip_trailing_commentary) are copied from
backend/app/main.py verbatim: they're presentation-layer glue specific to
turning a spec into a Prompt B call, not part of the spec/flow/prompts core,
so they live alongside the route that uses them here — same as main.py.
"""

import copy
import json
import os
import re

from fastapi import APIRouter, Depends, HTTPException

from app import flow
from app.llm.llm_core import llm_call_async
from app.prompts import build_prompt_a_system_prompt, build_prompt_b_system_prompt
from app.scaffolding.generator import generate_scaffold as _build_scaffold
from app.scaffolding.matcher import pick_template
from app.schemas import (
    ChatRequest, ChatResponse, Message,
    PrdRequest, PrdResponse,
    ScaffoldRequest, ScaffoldResponse,
)
from app.web_auth import require_user
from app.web_db import SessionLocal
from app import web_sessions as sessions

PROMPT_A_SYSTEM_PROMPT = build_prompt_a_system_prompt()
PROMPT_B_SYSTEM_PROMPT = build_prompt_b_system_prompt()

# M8 found Prompt B intermittently truncating mid-document on the local 3B
# model (as low as ~1,100 chars on a spec that should produce ~5,000). A full
# PRD across all 11 sections runs well under 2,000 tokens, so this cap is a
# generous multiple of that — high enough to never be the limiting factor,
# just ruling out Ollama's default as a variable.
_PRD_NUM_PREDICT = 4096


def _ollama_chat_url() -> str:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    return f"{base}/api/chat"


def _ollama_model() -> str:
    model = os.getenv("OLLAMA_MODEL")
    if not model:
        raise RuntimeError(
            "OLLAMA_MODEL is not set. Pull a model (e.g. `ollama pull llama3.1`) "
            "and set OLLAMA_MODEL to its name. See backend/.env.example."
        )
    return model


def _build_prompt_a_messages(spec: dict, history: list[Message], user_message: str) -> list[dict]:
    """Assemble messages for one Prompt A call, as plain dicts for llm_call_async.

    llm_call_async takes a flat messages list (no separate system_prompt arg,
    matching the reference), so the system prompt is messages[0] here.
    """
    return [
        {"role": "system", "content": PROMPT_A_SYSTEM_PROMPT},
        {"role": "user", "content": f"current_spec:\n{json.dumps(spec, indent=2)}"},
        *[{"role": m.role, "content": m.content} for m in history],
        {"role": "user", "content": user_message},
    ]


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


_MVP_FEATURES_MARKER = "[[RENDER:MVP_FEATURES]]"
_KNOWN_RISKS_MARKER = "[[RENDER:KNOWN_RISKS]]"


def _render_mvp_features_md(mvp_features) -> str:
    """Render the Must/Should/Could-have breakdown directly from the
    already-structured {name, priority} entries — no LLM transcription.

    M8 found the model unreliable at sorting mvp_features into the right P0/
    P1/P2 heading even when handed pre-grouped JSON and told not to re-sort
    (same failure class as the known-risks bug below). The data is already
    fully structured, so rendering it is pure formatting — the backend owns
    it outright rather than asking the model to transcribe it.
    """
    groups: dict[str, list[str]] = {"P0": [], "P1": [], "P2": []}
    if isinstance(mvp_features, list) and mvp_features not in ([], ["unspecified"]):
        for f in mvp_features:
            if isinstance(f, dict) and f.get("priority") in groups:
                groups[f["priority"]].append(f.get("name", ""))

    labels = {"P0": "Must-have (P0)", "P1": "Should-have (P1)", "P2": "Could-have (P2)"}
    blocks = []
    for tier in ("P0", "P1", "P2"):
        blocks.append(f"**{labels[tier]}:**")
        if groups[tier]:
            blocks.append("\n".join(f"- {name}" for name in groups[tier]))
        else:
            blocks.append("- None specified.")
    return "\n\n".join(blocks)


def _render_known_risks_md(known_risks) -> str:
    """Render the known-risks register grouped by impact, straight from the
    spec's {risk, impact, mitigation} entries — no LLM transcription.

    M8 found the model unreliable at placing risks under the right
    High/Medium/Low heading even when handed pre-grouped JSON and told not
    to re-sort — it shifted tiers, collapsed risks into one bucket, or
    invented a risk to fill an empty one. The data is already fully
    structured, so the backend renders it directly instead of trusting the
    model's own labels in its output.
    """
    groups: dict[str, list[dict]] = {"High": [], "Medium": [], "Low": []}
    if isinstance(known_risks, list) and known_risks not in ([], ["unspecified"]):
        for r in known_risks:
            if isinstance(r, dict) and r.get("impact") in groups:
                groups[r["impact"]].append(r)

    blocks = []
    for impact in ("High", "Medium", "Low"):
        blocks.append(f"**Known Risks ({impact}-Impact):**")
        if groups[impact]:
            for r in groups[impact]:
                risk = r.get("risk", "")
                mitigation = r.get("mitigation") or "unspecified"
                blocks.append(f"- **Risk:** {risk}\n  **Mitigation:** {mitigation}")
        else:
            blocks.append("- None identified.")
    return "\n\n".join(blocks)


def _insert_after_heading(text: str, keyword: str, block: str) -> str:
    """Insert `block` on its own line right after the first markdown heading
    whose text contains `keyword` (case-insensitive).

    Fallback for when the model doesn't emit the literal marker token it was
    asked to — appends to the end of the document if no matching heading is
    found either, so the correct content is never silently dropped.
    """
    match = re.search(rf"(?im)^#{{1,6}}[ \t]+.*{keyword}.*$", text)
    if not match:
        return text.rstrip() + f"\n\n{block}\n"
    insert_at = match.end()
    return text[:insert_at] + f"\n\n{block}\n" + text[insert_at:]


def _insert_rendered_blocks(prd_text: str, spec: dict) -> str:
    """Splice the deterministically-rendered mvp_features and known_risks
    blocks into the model's PRD text in place of the marker tokens Prompt B
    was instructed to emit, falling back to heading-based insertion if a
    marker is missing from the model's output."""
    mvp_md = _render_mvp_features_md(spec.get("scope_and_features", {}).get("mvp_features"))
    risks_md = _render_known_risks_md(spec.get("risks_assumptions", {}).get("known_risks"))

    if _MVP_FEATURES_MARKER in prd_text:
        prd_text = prd_text.replace(_MVP_FEATURES_MARKER, mvp_md, 1)
    else:
        prd_text = _insert_after_heading(prd_text, "scope", mvp_md)

    if _KNOWN_RISKS_MARKER in prd_text:
        prd_text = prd_text.replace(_KNOWN_RISKS_MARKER, risks_md, 1)
    else:
        prd_text = _insert_after_heading(prd_text, "risk", risks_md)

    return prd_text


def _prepare_spec_for_prd(spec: dict) -> str:
    """Restructure the spec into a pre-grouped user message for Prompt B.

    Extracts future_features into preamble text and lists any "unspecified"
    fields for the Open Questions section. mvp_features and known_risks are
    NOT sent for transcription at all — the model reliably ignores the
    "don't re-sort" instruction for grouped data (M8), so it's told to leave
    a literal marker in their place instead; _insert_rendered_blocks splices
    in the backend-rendered version after the call.
    """
    out = copy.deepcopy(spec)
    out.pop("_meta", None)

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

    scope = out.get("scope_and_features", {})

    # Rendered by the backend after the call (see _insert_rendered_blocks) —
    # not sent to the model at all, so there's nothing for it to re-sort.
    scope.pop("mvp_features", None)

    raw_future = scope.pop("future_features", [])
    if isinstance(raw_future, list) and raw_future not in ([], ["unspecified"]):
        future_block = "\n".join(f"  - {f}" for f in raw_future)
    else:
        future_block = "  (none specified)"

    risks = out.get("risks_assumptions", {})
    # Also rendered by the backend after the call — see above.
    risks.pop("known_risks", None)

    preamble = (
        "The specification below has been pre-processed. "
        "Transcribe these groupings directly into the PRD — do NOT re-sort or re-derive them.\n\n"
        "SCOPE SECTION — use exactly these subsections in this order:\n"
        f"  1. Must-have (P0) / Should-have (P1) / Could-have (P2): do NOT write this part\n"
        f"     yourself. Insert the exact literal line {_MVP_FEATURES_MARKER} on its own line\n"
        "     and nothing else — it will be replaced with the correct content automatically.\n"
        "  2. Future scope (post-MVP, not part of this release):\n"
        f"{future_block}\n"
        "  3. Explicitly out of scope: transcribe explicitly_out_of_scope from the JSON\n\n"
        "RISKS SECTION:\n"
        f"  Known risks: do NOT write this part yourself. Insert the exact literal line\n"
        f"  {_KNOWN_RISKS_MARKER} on its own line and nothing else — it will be replaced\n"
        "  with the correct content automatically.\n\n"
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
    """Strip a trailing plain-text paragraph models append after the final section."""
    text = text.rstrip()
    blocks = re.split(r"\n[ \t]*\n", text)
    if len(blocks) < 2:
        return text
    last = blocks[-1].strip()
    has_marker = re.search(r"(?m)^[ \t]*(?:#|-|\*|\d+\.|>|```|\|)", last)
    if not has_marker:
        return "\n\n".join(b for b in blocks[:-1] if b.strip())
    return text


_JSON_REPAIR_INSTRUCTION = (
    "Your last reply was not valid JSON. Reply again with ONLY a single valid "
    "JSON object matching the required schema — no markdown fences, no "
    "commentary before or after it."
)


async def _call_prompt_a_with_repair(messages: list[dict]) -> dict:
    """Call Prompt A and parse its JSON reply, retrying once on a parse failure.

    llm_call_async has no format="json" param (matches the ai-system
    reference exactly, which doesn't use Ollama's native JSON mode either) —
    small local models occasionally drift from JSON-only output as a result.
    This is a resilience layer on top, not a replacement for that constraint:
    one retry with an explicit "return valid JSON" instruction appended, then
    give up and surface a 502 like before.
    """
    raw = await llm_call_async(_ollama_chat_url(), _ollama_model(), messages, temperature=0.3)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    repair_messages = [
        *messages,
        {"role": "assistant", "content": raw},
        {"role": "user", "content": _JSON_REPAIR_INSTRUCTION},
    ]
    raw_retry = await llm_call_async(
        _ollama_chat_url(), _ollama_model(), repair_messages, temperature=0.3
    )
    try:
        return json.loads(raw_retry)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Model did not return valid JSON after a repair retry: {exc}",
        ) from exc


def setup_prd_routes() -> APIRouter:
    router = APIRouter(prefix="/api/prd", tags=["prd"])

    @router.post("/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest, user: str = Depends(require_user)) -> ChatResponse:
        db = SessionLocal()
        try:
            session = sessions.get_or_create(db, req.session_id, user)

            messages = _build_prompt_a_messages(session.spec, session.history, req.message)
            parsed = await _call_prompt_a_with_repair(messages)

            reply = parsed.get("reply_to_user", "")
            session.spec = flow.process_turn(
                session.spec,
                parsed.get("updated_spec"),
                req.message,
                history=session.history,
                _enable_grounding=True,
            )
            phase = session.spec["_meta"]["phase"]

            session.history.append(Message(role="user", content=req.message))
            session.history.append(Message(role="assistant", content=reply))

            sessions.save(db, req.session_id, user, session)

            return ChatResponse(reply=reply, phase=phase, spec=session.spec)
        finally:
            db.close()

    @router.post("/generate-prd", response_model=PrdResponse)
    async def generate_prd(req: PrdRequest, user: str = Depends(require_user)) -> PrdResponse:
        db = SessionLocal()
        try:
            session = sessions.get(db, req.session_id, user)
            if session is None:
                raise HTTPException(status_code=404, detail="No such session")

            missing = flow.missing_fields(session.spec)
            if missing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Spec is not complete — missing fields: {missing}",
                )

            user_content = _prepare_spec_for_prd(session.spec)
            prd_text = await llm_call_async(
                _ollama_chat_url(),
                _ollama_model(),
                [
                    {"role": "system", "content": PROMPT_B_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.6,
                num_predict=_PRD_NUM_PREDICT,
            )

            prd_text = _strip_trailing_commentary(_strip_md_fence(prd_text))
            prd_text = _insert_rendered_blocks(prd_text, session.spec)
            return PrdResponse(prd=prd_text)
        finally:
            db.close()

    @router.post("/generate-scaffold", response_model=ScaffoldResponse)
    async def generate_scaffold_route(
        req: ScaffoldRequest, user: str = Depends(require_user)
    ) -> ScaffoldResponse:
        db = SessionLocal()
        try:
            session = sessions.get(db, req.session_id, user)
            if session is None:
                raise HTTPException(status_code=404, detail="No such session")

            missing = flow.missing_fields(session.spec)
            if missing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Spec is not complete — missing fields: {missing}",
                )

            tech_stack = (
                session.spec.get("technical_requirements", {}).get("tech_stack_preference")
            )
            match = pick_template(tech_stack)
            result = _build_scaffold(session.spec, match)
            return ScaffoldResponse(**result)
        finally:
            db.close()

    return router
