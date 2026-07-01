"""Proper replacement for the stale test_409_gate in scripts/verify_m4.py.

The old test called a pre-M5 in-memory sessions API that no longer exists and
required a running server. These tests use FastAPI's TestClient with a mocked
sessions layer so they run anywhere, instantly, without a live server or Neon.

Tests covered:
  - /generate-prd returns 409 when the spec has missing fields
  - /generate-prd returns 200 when the spec is complete (mocked LLM)
  - /generate-scaffold returns 409 when the spec has missing fields
  - Both endpoints' 409 response bodies contain the missing-field list
"""

import pytest
from unittest.mock import AsyncMock, patch

from app import flow, sessions
from app.spec import initial_spec
from tests.conftest import make_complete_spec


SID = "prd-gate-test"


def _make_client_with_spec(chat_client, fake_sessions, spec: dict):
    """Seed fake_sessions with the given spec so endpoint tests can use it."""
    fake_sessions[SID] = sessions.Session(spec=spec, history=[])
    return chat_client


# ── /generate-prd 409 gate ────────────────────────────────────────────────────

class TestGeneratePrd409Gate:

    def test_incomplete_spec_returns_409(self, chat_client, fake_sessions):
        """POST /generate-prd on an incomplete spec must return 409 before the
        LLM is ever called. Replaces test_409_gate() from scripts/verify_m4.py."""
        _make_client_with_spec(chat_client, fake_sessions, initial_spec())

        resp = chat_client.post("/generate-prd", json={"session_id": SID})

        assert resp.status_code == 409, (
            f"Expected 409 for incomplete spec, got {resp.status_code}"
        )

    def test_409_body_contains_missing_fields_list(self, chat_client, fake_sessions):
        """The 409 detail must name the missing fields so the error is diagnosable."""
        _make_client_with_spec(chat_client, fake_sessions, initial_spec())

        resp = chat_client.post("/generate-prd", json={"session_id": SID})
        body = resp.json()

        assert "missing fields" in body["detail"].lower(), (
            f"Expected 'missing fields' in detail, got: {body['detail']!r}"
        )

    def test_partial_spec_still_returns_409(self, chat_client, fake_sessions):
        """Even one empty field is enough to trigger the gate."""
        spec = make_complete_spec()
        # Remove one field to make it incomplete
        spec["problem_and_vision"]["motivation"] = None
        _make_client_with_spec(chat_client, fake_sessions, spec)

        resp = chat_client.post("/generate-prd", json={"session_id": SID})

        assert resp.status_code == 409

    def test_complete_spec_returns_200(self, chat_client, fake_sessions):
        """POST /generate-prd on a complete spec must return 200 (LLM mocked)."""
        _make_client_with_spec(chat_client, fake_sessions, make_complete_spec())

        with patch("app.main.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "# PRD\n\nThis is the generated document."
            resp = chat_client.post("/generate-prd", json={"session_id": SID})

        assert resp.status_code == 200
        assert "prd" in resp.json()

    def test_unknown_session_returns_404(self, chat_client, fake_sessions):
        """/generate-prd on a session that doesn't exist must return 404."""
        resp = chat_client.post("/generate-prd", json={"session_id": "no-such-session"})

        assert resp.status_code == 404

    def test_lllm_not_called_on_incomplete_spec(self, chat_client, fake_sessions):
        """The LLM must never be called when the spec is incomplete — the gate
        fires before reaching the generate() call."""
        _make_client_with_spec(chat_client, fake_sessions, initial_spec())

        with patch("app.main.generate", new_callable=AsyncMock) as mock_gen:
            chat_client.post("/generate-prd", json={"session_id": SID})
            mock_gen.assert_not_called()


# ── /generate-scaffold 409 gate ───────────────────────────────────────────────

class TestGenerateScaffold409Gate:

    def test_incomplete_spec_returns_409(self, chat_client, fake_sessions):
        """POST /generate-scaffold on an incomplete spec must also return 409."""
        _make_client_with_spec(chat_client, fake_sessions, initial_spec())

        resp = chat_client.post("/generate-scaffold", json={"session_id": SID})

        assert resp.status_code == 409

    def test_409_body_contains_missing_fields_list(self, chat_client, fake_sessions):
        """/generate-scaffold 409 body must also name the missing fields."""
        _make_client_with_spec(chat_client, fake_sessions, initial_spec())

        resp = chat_client.post("/generate-scaffold", json={"session_id": SID})
        body = resp.json()

        assert "missing fields" in body["detail"].lower()

    def test_unknown_session_returns_404(self, chat_client, fake_sessions):
        resp = chat_client.post(
            "/generate-scaffold", json={"session_id": "no-such-session"}
        )
        assert resp.status_code == 404
