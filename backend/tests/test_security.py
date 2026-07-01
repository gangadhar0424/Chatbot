"""Milestone 9 — Security hardening tests.

Three test classes covering:
  1. Prompt-injection resistance — even if the model returns malicious output,
     the backend pipeline (recompute_meta, reject_future_sentinels,
     _strip_unknown_keys, field validators) must neutralise it.
  2. Input validation — oversized / malformed inputs are rejected at the
     schema layer (422) before reaching the LLM or DB.
  3. Rate limiting — 30/minute on /chat and 5/minute on /generate-prd and
     /generate-scaffold; N+1 requests return 429.

All tests use the shared chat_client / fake_sessions fixtures from conftest
(mocked DB, mocked sessions, no real Ollama calls). Rate-limit tests use a
separate TestClient instance whose limiter storage is pre-filled to the
production limit, so only one real HTTP call is needed to trigger 429.
"""

import json
import os
import pytest
from unittest.mock import AsyncMock, patch

from app import flow, sessions
from app.spec import initial_spec
from tests.conftest import make_complete_spec, model_json

SID = "sec-test"


def _chat(client, message, session_id=SID):
    return client.post("/chat", json={"session_id": session_id, "message": message})


def _seed(fake_sessions, spec, sid=SID):
    fake_sessions[sid] = sessions.Session(spec=spec, history=[])


# ── 1. Prompt-injection resistance ───────────────────────────────────────────

class TestPromptInjection:

    def test_phase_flip_with_single_field_filled_is_overridden(
        self, chat_client, fake_sessions
    ):
        """Model claims ready_for_prd after filling only one_liner.
        Backend recompute_meta must override to gathering."""
        with patch("app.main.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = model_json(
                {"problem_and_vision": {"one_liner": "A task app"}},
                reply="All done!",
                phase="ready_for_prd",
            )
            resp = _chat(chat_client, "Build me a task app")

        assert resp.status_code == 200
        body = resp.json()
        assert body["phase"] == "gathering", (
            "Backend must not accept model's ready_for_prd — spec is not complete"
        )
        assert body["spec"]["_meta"]["phase"] == "gathering"

    def test_fabricated_completed_sections_in_meta_corrected(
        self, chat_client, fake_sessions
    ):
        """Model sets _meta.completed_sections to all 9 sections and
        current_section to risks_assumptions, but actual fields are all null.
        recompute_meta must derive the correct state from the actual fields."""
        fabricated_meta = {
            "current_section": "risks_assumptions",
            "completed_sections": list(flow.SECTION_ORDER),
            "questions_asked_this_section": 0,
            "phase": "ready_for_prd",
        }
        with patch("app.main.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = model_json(
                {"_meta": fabricated_meta},
                reply="All sections done!",
                phase="ready_for_prd",
            )
            resp = _chat(chat_client, "Mark everything complete")

        assert resp.status_code == 200
        meta = resp.json()["spec"]["_meta"]
        assert meta["current_section"] == "problem_and_vision", (
            "recompute_meta must land on problem_and_vision — all fields still null"
        )
        assert meta["phase"] == "gathering"
        assert meta["completed_sections"] == []

    def test_backward_section_jump_blocked(self, chat_client, fake_sessions):
        """Session seeded at scope_and_features (sections 1-2 complete).
        Model returns current_section=problem_and_vision (backward jump).
        recompute_meta must keep us at scope_and_features."""
        template = initial_spec()
        seed = make_complete_spec()
        # Clear sections 3–9 back to initial empty state
        for section in flow.SECTION_ORDER[2:]:
            for field in flow.SECTION_FIELDS[section]:
                seed[section][field] = template[section][field]
        seed["_meta"] = {
            "current_section": "scope_and_features",
            "completed_sections": ["problem_and_vision", "users_and_use_cases"],
            "questions_asked_this_section": 0,
            "phase": "gathering",
        }
        _seed(fake_sessions, seed)

        backward_meta = {
            "current_section": "problem_and_vision",
            "completed_sections": [],
            "questions_asked_this_section": 0,
            "phase": "gathering",
        }
        with patch("app.main.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = model_json(
                {"_meta": backward_meta},
                reply="Let me re-ask about your project.",
            )
            resp = _chat(chat_client, "Go back to the beginning")

        assert resp.status_code == 200
        meta = resp.json()["spec"]["_meta"]
        assert meta["current_section"] == "scope_and_features", (
            "Backend must not allow a backward section jump"
        )

    def test_extra_top_level_fields_stripped(self, chat_client, fake_sessions):
        """Model adds an unknown top-level key to updated_spec.
        _strip_unknown_keys must remove it before the spec is saved."""
        injected_updates = {
            "problem_and_vision": {"one_liner": "A task app"},
            "_backdoor": "injected",
            "_extra": {"nested": "data"},
        }
        with patch("app.main.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = json.dumps({
                "updated_spec": injected_updates,
                "reply_to_user": "Got it.",
                "phase": "gathering",
            })
            resp = _chat(chat_client, "A task app for teams")

        assert resp.status_code == 200
        spec = resp.json()["spec"]
        assert "_backdoor" not in spec, "Unknown top-level key must be stripped"
        assert "_extra" not in spec, "Unknown top-level key must be stripped"

    def test_extra_section_level_fields_stripped(self, chat_client, fake_sessions):
        """Model adds an unknown field inside a section dict.
        _strip_unknown_keys must remove it."""
        injected_updates = {
            "problem_and_vision": {
                "one_liner": "A task app",
                "_injected": "evil_value",
            }
        }
        with patch("app.main.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = json.dumps({
                "updated_spec": injected_updates,
                "reply_to_user": "Got it.",
                "phase": "gathering",
            })
            resp = _chat(chat_client, "A task app for teams")

        assert resp.status_code == 200
        pv = resp.json()["spec"]["problem_and_vision"]
        assert "_injected" not in pv, "Unknown section-level field must be stripped"

    def test_reply_to_user_phase_text_does_not_affect_spec(
        self, chat_client, fake_sessions
    ):
        """Model embeds 'ready_for_prd' in reply_to_user and sets the outer
        phase field — but the spec is still incomplete.
        Backend must read phase from spec._meta, not from the outer field."""
        with patch("app.main.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = json.dumps({
                "updated_spec": {
                    "problem_and_vision": {"one_liner": "task app"}
                },
                "reply_to_user": "Setting phase: ready_for_prd. All done!",
                "phase": "ready_for_prd",
            })
            resp = _chat(chat_client, "task app")

        assert resp.status_code == 200
        body = resp.json()
        assert body["phase"] == "gathering", (
            "Phase in response must come from spec._meta, not from model's outer phase field"
        )
        assert body["spec"]["_meta"]["phase"] == "gathering"


# ── 2. Input validation ───────────────────────────────────────────────────────

class TestInputValidation:

    def test_chat_oversized_message_rejected(self, chat_client):
        """A message longer than 16 384 chars must be rejected with 422
        before reaching the LLM."""
        huge = "x" * 16_385
        with patch("app.main.generate", new_callable=AsyncMock) as mock_gen:
            resp = chat_client.post(
                "/chat", json={"session_id": SID, "message": huge}
            )
            mock_gen.assert_not_called()

        assert resp.status_code == 422, (
            f"Expected 422 for oversized message, got {resp.status_code}"
        )

    def test_chat_malformed_session_id_rejected(self, chat_client):
        """A session_id containing path-traversal or injection characters
        must be rejected with 422."""
        bad_ids = ["../../../etc", "'; DROP TABLE sessions; --", "id with spaces"]
        for bad in bad_ids:
            resp = chat_client.post(
                "/chat", json={"session_id": bad, "message": "hi"}
            )
            assert resp.status_code == 422, (
                f"Expected 422 for session_id {bad!r}, got {resp.status_code}"
            )

    def test_prd_malformed_session_id_rejected(self, chat_client):
        """Malformed session_id on /generate-prd must also return 422."""
        resp = chat_client.post(
            "/generate-prd", json={"session_id": "../../../etc/passwd"}
        )
        assert resp.status_code == 422

    def test_scaffold_malformed_session_id_rejected(self, chat_client):
        """Malformed session_id on /generate-scaffold must also return 422."""
        resp = chat_client.post(
            "/generate-scaffold", json={"session_id": "'; DROP TABLE--"}
        )
        assert resp.status_code == 422


# ── 3. Rate limiting ──────────────────────────────────────────────────────────
#
# Strategy: send N real TestClient requests (all in-process, no network) to
# exhaust the production limit, then assert the N+1th returns 429.
# The reset_rate_limiter autouse fixture clears storage before each test so
# the counter starts at zero regardless of what earlier tests did.
#
# Production limits (no env-var override in conftest):
#   /chat            → 30/minute
#   /generate-prd    →  5/minute
#   /generate-scaffold →  5/minute

class TestRateLimiting:

    def test_chat_rate_limit_returns_429(self, chat_client, fake_sessions):
        """The 31st /chat request from the same IP within a minute returns 429."""
        with patch("app.main.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = model_json({}, "ok")
            for i in range(30):
                r = _chat(chat_client, "hi", session_id=f"rl{i}")
                assert r.status_code == 200, (
                    f"Request {i + 1} should succeed, got {r.status_code}"
                )
            # 31st request — counter now at 30/30 → 429
            r = _chat(chat_client, "hi", session_id="rl30")
        assert r.status_code == 429, (
            f"Expected 429 on request 31, got {r.status_code}"
        )

    def test_prd_rate_limit_returns_429(self, chat_client):
        """The 6th /generate-prd request from the same IP within a minute returns 429.
        Uses a non-existent session so each request returns 404 cheaply."""
        for i in range(5):
            r = chat_client.post("/generate-prd", json={"session_id": "no-such"})
            assert r.status_code == 404, (
                f"Request {i + 1} should be 404 (session not found), got {r.status_code}"
            )
        r = chat_client.post("/generate-prd", json={"session_id": "no-such"})
        assert r.status_code == 429, (
            f"Expected 429 on request 6, got {r.status_code}"
        )

    def test_scaffold_rate_limit_returns_429(self, chat_client):
        """The 6th /generate-scaffold request from the same IP within a minute returns 429."""
        for i in range(5):
            r = chat_client.post("/generate-scaffold", json={"session_id": "no-such"})
            assert r.status_code == 404, (
                f"Request {i + 1} should be 404 (session not found), got {r.status_code}"
            )
        r = chat_client.post("/generate-scaffold", json={"session_id": "no-such"})
        assert r.status_code == 429, (
            f"Expected 429 on request 6, got {r.status_code}"
        )
