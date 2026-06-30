"""Seed a completed spec and generate the PRD via a direct streaming Ollama call.

Uses the same complete-spec fixture as verify_m4.py. Streams tokens so we see
progress and don't hit a read timeout on a slow local model.
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv()

from app import flow, sessions
from app.spec import initial_spec
from app.prompts import build_prompt_b_system_prompt
from app.main import _prepare_spec_for_prd, _strip_md_fence, _strip_trailing_commentary

import httpx


def make_complete_spec() -> dict:
    spec = initial_spec()
    spec["problem_and_vision"] = {
        "one_liner": "A task management app for remote software teams",
        "problem_statement": (
            "Remote teams using email and spreadsheets to track work constantly "
            "miss deadlines because there is no single shared view of who owns "
            "what and what is blocked."
        ),
        "business_goals": (
            "Become the go-to lightweight PM tool for teams of 5-20 that find "
            "Jira too heavy. Target 50 paying teams within 6 months of launch."
        ),
        "motivation": (
            "Founder ran a 12-person remote team for three years and watched "
            "every sprint planning turn into a two-hour catch-up on who had done "
            "what since the last meeting."
        ),
        "success_metrics": [
            "30% reduction in self-reported missed deadlines after 90 days",
            "50 paying teams at month 6",
            "Weekly active user rate above 70% among paid seats",
        ],
    }
    spec["users_and_use_cases"] = {
        "target_users": "Remote software teams of 5-20 people, especially startups and small agencies",
        "primary_use_cases": [
            "Create, assign, and prioritise tasks within a team board",
            "Track task status from To Do through In Progress to Done",
            "Leave comments and attach files to individual tasks",
            "Get a daily digest of what is blocked or overdue",
        ],
        "user_personas": [
            "Team lead: sets priorities, monitors blockers, runs weekly reviews",
            "Individual contributor: picks up tasks, updates status, flags blockers",
        ],
    }
    spec["scope_and_features"] = {
        "mvp_features": [
            {"name": "User authentication (email + password)", "priority": "P0"},
            {"name": "Team workspace with invite by email", "priority": "P0"},
            {"name": "Kanban task board (To Do / In Progress / Done)", "priority": "P0"},
            {"name": "Task detail view (title, description, assignee, due date, status)", "priority": "P0"},
            {"name": "In-task comments and file attachments", "priority": "P1"},
            {"name": "Daily email digest of overdue and blocked tasks", "priority": "P1"},
            {"name": "Basic search across tasks", "priority": "P2"},
        ],
        "future_features": [
            "Time tracking per task",
            "Gantt / timeline view",
            "Native mobile apps (iOS and Android)",
            "Two-way GitHub Issues sync",
            "AI-generated task summaries",
        ],
        "explicitly_out_of_scope": [
            "Resource capacity planning",
            "Invoicing or billing features",
            "Built-in video conferencing",
        ],
    }
    spec["technical_requirements"] = {
        "tech_stack_preference": "React (Next.js) frontend, FastAPI (Python) backend, PostgreSQL database",
        "integrations": [
            "Slack (post notifications when tasks are overdue)",
            "GitHub (link commits to tasks)",
        ],
        "data_model": (
            "Core entities: User, Team, TeamMembership, Task, Comment, Attachment. "
            "Tasks belong to a Team; Comments and Attachments belong to a Task; "
            "TeamMembership is a join table between User and Team with a role field "
            "(owner / member)."
        ),
        "non_functional_requirements": [
            "API p95 latency under 200 ms for task list and board endpoints",
            "Support up to 500 concurrent users in the first year",
            "Data encrypted at rest (AES-256) and in transit (TLS 1.2+)",
        ],
        "compliance_requirements": [
            "GDPR applies -- users in the EU will store personal data (names, emails, "
            "work content). Need a privacy policy, data-processing agreement template, "
            "and a way for users to export or delete their data."
        ],
    }
    spec["ux_design"] = {
        "platform": "Web (desktop-first, responsive down to tablet)",
        "design_preferences": (
            "Clean and minimal -- think Linear or Height. Neutral palette with a "
            "single brand accent colour. No heavy illustrations."
        ),
        "accessibility_needs": "WCAG 2.1 AA compliance required from launch",
    }
    spec["deployment_infra"] = {
        "deployment_target": "AWS (ECS Fargate for the API, S3 + CloudFront for the frontend)",
        "environments": "dev (local Docker Compose), staging (auto-deploy on merge to main), prod (manual promote)",
        "cicd_needs": (
            "GitHub Actions: lint + test on every PR, build and push Docker image on "
            "merge to main, deploy to staging automatically, one-click promote to prod."
        ),
    }
    spec["timeline_resources"] = {
        "timeline": (
            "MVP in 4 months: month 1 auth + data model, month 2 board + task detail, "
            "month 3 comments + digest email + search, month 4 hardening + beta."
        ),
        "budget": "~$80,000 total: $60k engineering, $10k design, $10k infra + tools for year 1",
        "team_size_roles": (
            "2 full-stack engineers (one doubles as tech lead), "
            "1 product designer (part-time months 1-3), "
            "1 founder acting as product manager"
        ),
    }
    spec["maintenance_ops"] = {
        "maintenance_plan": (
            "Fortnightly dependency updates via Dependabot PRs reviewed by the tech lead. "
            "Quarterly security audit. On-call rotation between the two engineers."
        ),
        "monitoring_logging": (
            "Datadog APM for traces and metrics; structured JSON logs shipped to Datadog "
            "Log Management. Alerts on p95 latency > 500 ms and error rate > 1%."
        ),
        "support_plan": (
            "Email support (support@) with a 48-hour SLA during beta. "
            "In-app feedback widget (Canny) for feature requests. "
            "Public status page (Statuspage.io)."
        ),
    }
    spec["risks_assumptions"] = {
        "known_risks": [
            {
                "risk": "Low initial adoption -- teams reluctant to migrate away from existing tools",
                "impact": "High",
                "mitigation": (
                    "Run a 30-day free beta with 10 hand-picked teams, gather NPS weekly, "
                    "and use feedback to fix the top friction points before public launch."
                ),
            },
            {
                "risk": "Scope creep delaying MVP",
                "impact": "Medium",
                "mitigation": (
                    "Lock the MVP feature list in a signed-off PRD and require a formal "
                    "change-request with re-estimated timeline before any addition."
                ),
            },
            {
                "risk": "GDPR non-compliance before EU launch",
                "impact": "High",
                "mitigation": (
                    "Engage a GDPR consultant in month 1, build data-export and "
                    "account-deletion flows into the MVP, and complete a DPIA before launch."
                ),
            },
        ],
        "assumptions": [
            "Target users have reliable internet access and use a modern desktop browser",
            "Slack and GitHub integrations cover the majority of the target audience's toolchain",
            "A freemium pricing model (free up to 5 users, paid above that) will convert beta teams",
        ],
        "dependencies": [
            "Slack API availability and rate limits",
            "GitHub API for commit linking",
            "AWS service availability in eu-west-1 and us-east-1",
        ],
    }
    spec["_meta"] = {
        "current_section": "risks_assumptions",
        "completed_sections": list(flow.SECTION_ORDER),
        "questions_asked_this_section": 3,
        "phase": "ready_for_prd",
    }
    return spec


async def main() -> None:
    spec = make_complete_spec()

    missing = flow.missing_fields(spec)
    if missing:
        print(f"ERROR: spec has {len(missing)} missing fields: {missing}")
        sys.exit(1)

    model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    system_prompt = build_prompt_b_system_prompt()

    user_content = _prepare_spec_for_prd(spec)

    print(f"Spec complete -- 0 missing fields. Calling Prompt B ({model}) with streaming...\n")
    print("-" * 60)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": True,
        "options": {"temperature": 0.6},
    }

    chunks: list[str] = []
    # No timeout -- let the model take as long as it needs.
    async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
        async with client.stream("POST", f"{base_url}/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                token = data.get("message", {}).get("content", "")
                if token:
                    print(token, end="", flush=True)
                    chunks.append(token)
                if data.get("done"):
                    break

    prd = _strip_trailing_commentary(_strip_md_fence("".join(chunks)))
    print("\n" + "-" * 60)

    # Save alongside the script so the result is easy to inspect.
    out_path = os.path.join(os.path.dirname(__file__), "prd_output.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(prd)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
