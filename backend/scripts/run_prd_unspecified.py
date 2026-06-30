"""Verify that unspecified fields appear by name in 'Open questions / to be determined'.

Uses the same complete-spec fixture as run_prd.py with three fields deliberately
set to their sentinel values — exactly what happens when a user hits 'Not sure':
  - motivation          -> "unspecified"   (single-value field)
  - user_personas       -> ["unspecified"] (list field)
  - budget              -> "unspecified"   (single-value field)

Generates the PRD and prints the Open Questions section so we can confirm the
three field names appear there rather than being silently dropped.
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

from app import flow
from app.spec import initial_spec
from app.prompts import build_prompt_b_system_prompt
from app.main import _prepare_spec_for_prd, _strip_md_fence, _strip_trailing_commentary

import httpx


def make_spec_with_skips() -> dict:
    """Complete spec with three fields set to explicit 'unspecified' sentinels."""
    spec = initial_spec()
    spec["problem_and_vision"] = {
        "one_liner": "A task management app for remote software teams",
        "problem_statement": (
            "Remote teams using email and spreadsheets miss deadlines because "
            "there is no single shared view of who owns what and what is blocked."
        ),
        "business_goals": (
            "Become the go-to lightweight PM tool for small remote teams. "
            "Target 50 paying teams within 6 months of launch."
        ),
        "motivation": "unspecified",           # <-- SKIP 1: user hit "Not sure"
        "success_metrics": [
            "30% reduction in missed deadlines after 90 days",
            "50 paying teams at month 6",
        ],
    }
    spec["users_and_use_cases"] = {
        "target_users": "Remote software teams of 5-20 people",
        "primary_use_cases": [
            "Create, assign, and track tasks on a shared board",
            "Get notified about blocked or overdue work",
        ],
        "user_personas": ["unspecified"],      # <-- SKIP 2: user hit "Not sure"
    }
    spec["scope_and_features"] = {
        "mvp_features": [
            {"name": "User authentication", "priority": "P0"},
            {"name": "Kanban task board", "priority": "P0"},
            {"name": "Task detail view", "priority": "P0"},
            {"name": "Daily email digest", "priority": "P1"},
        ],
        "future_features": ["Mobile app", "GitHub sync"],
        "explicitly_out_of_scope": ["Invoicing", "Video conferencing"],
    }
    spec["technical_requirements"] = {
        "tech_stack_preference": "React + FastAPI + PostgreSQL",
        "integrations": ["Slack"],
        "data_model": "User, Team, Task, Comment",
        "non_functional_requirements": ["99.9% uptime", "p95 latency < 200ms"],
        "compliance_requirements": ["No regulations apply"],
    }
    spec["ux_design"] = {
        "platform": "Web",
        "design_preferences": "Clean and minimal",
        "accessibility_needs": "WCAG 2.1 AA",
    }
    spec["deployment_infra"] = {
        "deployment_target": "AWS",
        "environments": "dev, staging, prod",
        "cicd_needs": "GitHub Actions",
    }
    spec["timeline_resources"] = {
        "timeline": "4 months to MVP",
        "budget": "unspecified",               # <-- SKIP 3: user hit "Not sure"
        "team_size_roles": "2 engineers, 1 designer",
    }
    spec["maintenance_ops"] = {
        "maintenance_plan": "Monthly dependency updates",
        "monitoring_logging": "Datadog",
        "support_plan": "Email support, 48h SLA",
    }
    spec["risks_assumptions"] = {
        "known_risks": [
            {"risk": "Low adoption", "impact": "High",
             "mitigation": "30-day free beta with 10 teams"},
        ],
        "assumptions": ["Users have stable internet access"],
        "dependencies": ["Slack API", "AWS availability"],
    }
    spec["_meta"] = {
        "current_section": "risks_assumptions",
        "completed_sections": list(flow.SECTION_ORDER),
        "questions_asked_this_section": 2,
        "phase": "ready_for_prd",
    }
    return spec


async def main() -> None:
    spec = make_spec_with_skips()

    # Confirm the three sentinels are present.
    skipped = [
        f for f in flow.missing_fields(spec)
    ]
    assert not skipped, f"Unexpected truly-empty fields: {skipped}"

    sentinels = {
        "problem_and_vision.motivation":  spec["problem_and_vision"]["motivation"],
        "users_and_use_cases.user_personas": spec["users_and_use_cases"]["user_personas"],
        "timeline_resources.budget":      spec["timeline_resources"]["budget"],
    }
    print("Sentinel fields (should say unspecified):")
    for k, v in sentinels.items():
        print(f"  {k}: {v!r}")

    model    = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

    user_content  = _prepare_spec_for_prd(spec)
    system_prompt = build_prompt_b_system_prompt()

    print(f"\nCalling Prompt B ({model}) — streaming...\n")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ],
        "stream": True,
        "options": {"temperature": 0.6},
    }

    chunks: list[str] = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
        async with client.stream("POST", f"{base_url}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                data  = json.loads(line)
                token = data.get("message", {}).get("content", "")
                if token:
                    chunks.append(token)
                if data.get("done"):
                    break

    prd = _strip_trailing_commentary(_strip_md_fence("".join(chunks)))

    # --- Extract and print the Open Questions section -----------------------
    print("=" * 60)
    print("FULL PRD (for reference):")
    print("=" * 60)
    print(prd)
    print()

    # Find the Open Questions section (case-insensitive, handles slight wording variants).
    import re
    match = re.search(
        r"(##\s*(?:open questions|to be determined)[^\n]*\n.*?)(?=\n##\s|\Z)",
        prd,
        re.IGNORECASE | re.DOTALL,
    )
    print("=" * 60)
    if match:
        print("OPEN QUESTIONS SECTION:")
        print("=" * 60)
        print(match.group(1).strip())
    else:
        print("WARNING: No 'Open questions' section found in output.")
        print("=" * 60)

    # Save full PRD.
    out_path = os.path.join(os.path.dirname(__file__), "prd_unspecified.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(prd)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
