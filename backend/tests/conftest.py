"""Shared fixtures and helpers for the Milestone 7 test suite.

DATABASE_URL must be set before any app.* imports because app.db reads it at
module level. We point it at a fake Postgres URL so the engine object can be
created (asyncpg is installed), but get_db is always overridden in tests so no
real connection is ever made — Neon is never touched.
"""

import json
import os

# Must come before any app.* import.
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/testdb"

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.db import get_db
from app import flow, sessions
from app.spec import initial_spec


# ── Shared spec fixtures ──────────────────────────────────────────────────────

def make_complete_spec() -> dict:
    """Fully filled spec — every field has a real value or explicit sentinel.

    Adapted from scripts/verify_m4.py so the 409-gate and PRD tests have a
    consistent baseline. Two fields are left intentionally weak so edit tests
    can upgrade them:
      - 'User authentication' at P1  (can be bumped to P0)
      - known_risk mitigation = 'unspecified'  (can receive a real plan)
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
            {"name": "User authentication", "priority": "P1"},
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
                "mitigation": "unspecified",
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


@pytest.fixture
def complete_spec():
    return make_complete_spec()


# ── E2E client fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def fake_sessions():
    """In-memory session store, reset per test."""
    return {}


@pytest.fixture
def chat_client(fake_sessions):
    """TestClient with DB dependency and sessions layer fully mocked.

    No real Postgres connection is ever made. Sessions persist across turns
    within one test via the fake_sessions dict.
    """
    async def fake_get_db():
        yield None  # sessions layer is mocked; db arg is never used

    async def fake_get_or_create(db, session_id):
        if session_id not in fake_sessions:
            fake_sessions[session_id] = sessions.Session(
                spec=initial_spec(), history=[]
            )
        return fake_sessions[session_id]

    async def fake_get(db, session_id):
        return fake_sessions.get(session_id)

    async def fake_save(db, session_id, session):
        fake_sessions[session_id] = session

    app.dependency_overrides[get_db] = fake_get_db

    with (
        patch("app.sessions.get_or_create", fake_get_or_create),
        patch("app.sessions.get", fake_get),
        patch("app.sessions.save", fake_save),
    ):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()


# ── LLM mock helper ───────────────────────────────────────────────────────────

def model_json(spec_updates: dict, reply: str, phase: str = "gathering") -> str:
    """Build the JSON string a mocked generate() would return for one turn."""
    return json.dumps({
        "updated_spec": spec_updates,
        "reply_to_user": reply,
        "phase": phase,
    })
