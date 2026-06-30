"""
Milestone 4 verification -- two targeted checks:

1. 409 gate: POST /generate-prd against an incomplete spec must return 409
   with the list of missing fields (no Ollama needed -- the gate fires before
   the LLM is called).

2. Structured-field edit: flow.process_turn correctly updates a feature
   priority (P1 -> P0) and a risk mitigation when the model returns revised
   values, without corrupting the object shape or flipping phase away from
   ready_for_prd.

NOTE (M5 staleness): test_409_gate() calls the pre-M5 in-memory sessions API
(sessions.get_or_create(sid) without a db parameter) which no longer exists.
That test will fail until updated to seed a session via POST /chat or by
injecting a mock AsyncSession. test_structured_field_edit() is unaffected --
it only calls flow.process_turn directly with no sessions dependency.
"""

import json
import sys

from fastapi.testclient import TestClient

# Make sure the backend package is importable when run from the backend/ dir.
sys.path.insert(0, ".")

from app import flow, sessions
from app.main import app
from app.spec import initial_spec


# ─── helpers ─────────────────────────────────────────────────────────────────

def make_complete_spec() -> dict:
    """A fully filled spec fixture with deliberately weak initial values
    for the two fields this test will edit:
      - 'User authentication' at P1  (will be bumped to P0)
      - known_risk mitigation = 'unspecified'  (will be given a real plan)
    """
    spec = initial_spec()
    spec["problem_and_vision"] = {
        "one_liner": "A task management app for remote teams",
        "problem_statement": "Teams lose track of work without a shared system",
        "business_goals": "Reduce missed deadlines by 30%",
        "motivation": "Founder experienced this pain personally",
        "success_metrics": ["30% fewer missed deadlines", "50 paying teams in 6 months"],
    }
    spec["users_and_use_cases"] = {
        "target_users": "Remote software teams of 5-20 people",
        "primary_use_cases": ["Create and assign tasks", "Track progress"],
        "user_personas": ["Team lead", "Individual contributor"],
    }
    spec["scope_and_features"] = {
        "mvp_features": [
            {"name": "User authentication", "priority": "P1"},   # ← edit target
            {"name": "Task board", "priority": "P0"},
        ],
        "future_features": ["Time tracking"],
        "explicitly_out_of_scope": ["Mobile app"],
    }
    spec["technical_requirements"] = {
        "tech_stack_preference": "React + FastAPI",
        "integrations": ["Slack"],
        "data_model": "Users, Teams, Tasks, Comments",
        "non_functional_requirements": ["99.9% uptime"],
        "compliance_requirements": ["No regulations apply"],
    }
    spec["ux_design"] = {
        "platform": "Web",
        "design_preferences": "Clean, minimal",
        "accessibility_needs": "WCAG 2.1 AA",
    }
    spec["deployment_infra"] = {
        "deployment_target": "AWS",
        "environments": "dev, staging, prod",
        "cicd_needs": "GitHub Actions",
    }
    spec["timeline_resources"] = {
        "timeline": "6 months",
        "budget": "$50,000",
        "team_size_roles": "2 engineers, 1 designer",
    }
    spec["maintenance_ops"] = {
        "maintenance_plan": "Monthly dependency updates",
        "monitoring_logging": "Datadog",
        "support_plan": "Email support, 48 h response",
    }
    spec["risks_assumptions"] = {
        "known_risks": [
            {
                "risk": "Low initial adoption",
                "impact": "High",
                "mitigation": "unspecified",   # ← edit target
            }
        ],
        "assumptions": ["Users have stable internet"],
        "dependencies": ["Slack API availability"],
    }
    spec["_meta"] = {
        "current_section": "risks_assumptions",
        "completed_sections": list(flow.SECTION_ORDER),
        "questions_asked_this_section": 3,
        "phase": "ready_for_prd",
    }
    return spec


def banner(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


# ─── Test 1: 409 gate ────────────────────────────────────────────────────────

def test_409_gate() -> None:
    banner("TEST 1 -- 409 gate: /generate-prd with incomplete spec")

    client = TestClient(app)

    # Fresh empty session -- every field is null / [].
    sid = "m4-verify-409"
    sessions.get_or_create(sid)

    empty_fields = flow.missing_fields(sessions.get(sid).spec)
    print(f"\nSession spec has {len(empty_fields)} empty fields.")
    print(f"First 5: {empty_fields[:5]}")

    resp = client.post("/generate-prd", json={"session_id": sid})

    print(f"\nPOST /generate-prd  ->  HTTP {resp.status_code}")
    print("Response body:")
    print(json.dumps(resp.json(), indent=2))

    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}"
    body = resp.json()
    assert "missing fields" in body["detail"].lower(), \
        "Detail message should list missing fields"

    print("\n[OK]  Gate fired -- 409 returned before the LLM was ever called.")
    print("[OK]  'detail' carries the missing-field list so the error is diagnosable.")


# ─── Test 2: Structured-field edit via process_turn ─────────────────────────

def test_structured_field_edit() -> None:
    banner("TEST 2 -- Structured-field edit (priority P1->P0, risk mitigation)")

    prev_spec = make_complete_spec()

    print("\nBEFORE  (what the confirm screen shows):")
    print("  mvp_features :", json.dumps(prev_spec["scope_and_features"]["mvp_features"], indent=4))
    print("  known_risks  :", json.dumps(prev_spec["risks_assumptions"]["known_risks"], indent=4))

    # ── What Prompt A would return when the user says:
    #    "Actually, user authentication should be must-have (P0), and the
    #     mitigation for the adoption risk is: run a 30-day beta with 5 teams."
    #
    # The model returns only the changed sections; deep_merge preserves the rest.
    simulated_model_extraction = {
        "scope_and_features": {
            "mvp_features": [
                {"name": "User authentication", "priority": "P0"},   # upgraded
                {"name": "Task board", "priority": "P0"},
            ],
        },
        "risks_assumptions": {
            "known_risks": [
                {
                    "risk": "Low initial adoption",
                    "impact": "High",
                    "mitigation": "Run a 30-day beta with 5 teams before public launch",
                }
            ],
        },
    }

    user_text = (
        "Actually, user authentication should be must-have (P0), and the "
        "mitigation for the adoption risk is: run a 30-day beta with 5 teams."
    )

    # process_turn: deep_merge -> reject_future_sentinels -> normalize_structured
    # -> normalize_sentinel_shapes -> recompute_meta
    updated_spec = flow.process_turn(prev_spec, simulated_model_extraction, user_text)

    feats = updated_spec["scope_and_features"]["mvp_features"]
    risks = updated_spec["risks_assumptions"]["known_risks"]
    phase = updated_spec["_meta"]["phase"]

    print("\nAFTER  process_turn (what the confirm screen re-renders):")
    print("  mvp_features :", json.dumps(feats, indent=4))
    print("  known_risks  :", json.dumps(risks, indent=4))
    print(f"  phase        : {phase}")

    # ── Priority assertion
    auth = next(f for f in feats if f["name"] == "User authentication")
    assert auth["priority"] == "P0", f"Priority not updated: {auth}"
    assert set(auth.keys()) == {"name", "priority"}, f"mvp_feature shape corrupted: {auth}"

    # ── Risk mitigation assertion
    r = risks[0]
    assert r["mitigation"] == "Run a 30-day beta with 5 teams before public launch"
    assert r["impact"] == "High",  f"impact field changed unexpectedly: {r}"
    assert r["risk"]   == "Low initial adoption", f"risk text changed: {r}"
    assert set(r.keys()) == {"risk", "impact", "mitigation"}, \
        f"known_risk shape corrupted: {r}"

    # ── Phase stays ready_for_prd -- all fields still filled
    assert phase == "ready_for_prd", \
        f"Phase unexpectedly left ready_for_prd: {phase}"

    print("\n[OK]  Priority updated P1 -> P0.")
    print("[OK]  mvp_feature object shape intact  {name, priority}.")
    print("[OK]  Risk mitigation updated with real text.")
    print("[OK]  known_risk object shape intact  {risk, impact, mitigation}.")
    print("[OK]  Phase stayed ready_for_prd -> confirm screen re-shows automatically.")

    # ── Show the grouping SpecSummary.tsx would produce
    groups: dict[str, list[str]] = {"P0": [], "P1": [], "P2": []}
    for f in feats:
        groups[f["priority"]].append(f["name"])
    labels = {"P0": "Must-have (P0)", "P1": "Should-have (P1)", "P2": "Nice-to-have (P2)"}
    print("\nSpecSummary grouping:")
    for p in ["P0", "P1", "P2"]:
        if groups[p]:
            print(f"  [{labels[p]}]  {', '.join(groups[p])}")
    print("  -> 'User authentication' is now in Must-have, not Should-have.")


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_409_gate()
    test_structured_field_edit()
    banner("All checks passed")
