"""Regression tests for the 4 known bugs caught during manual testing.

Each class targets one bug. Tests call backend functions directly — no running
server, no LLM, no DB. Imports are pure Python.
"""

import copy
import json

import pytest

from app import flow
from app.main import _prepare_spec_for_prd
from app.spec import initial_spec


# ── Bug 1: Premature section completion ──────────────────────────────────────
#
# M3 root cause: the completion check only verified required fields, so sections
# advanced while optional fields (motivation, success_metrics, user_personas,
# etc.) were still null / []. The fix: every field — required AND optional —
# must hold a real value or an explicit sentinel before the section completes.

class TestPrematureSectionCompletion:

    def test_section_incomplete_while_optional_string_field_is_null(self):
        """is_section_complete returns False when an optional string field is null."""
        spec = initial_spec()
        spec["problem_and_vision"]["one_liner"] = "A task app"
        spec["problem_and_vision"]["problem_statement"] = "Teams lose track"
        spec["problem_and_vision"]["business_goals"] = "Reduce missed deadlines"
        # motivation is None (optional, but still required for completion)

        assert not flow.is_section_complete(spec, "problem_and_vision"), (
            "Section must not complete while optional field 'motivation' is still None"
        )

    def test_section_incomplete_while_optional_list_field_is_empty(self):
        """is_section_complete returns False when an optional list field is []."""
        spec = initial_spec()
        spec["problem_and_vision"]["one_liner"] = "A task app"
        spec["problem_and_vision"]["problem_statement"] = "Teams lose track"
        spec["problem_and_vision"]["business_goals"] = "Reduce missed deadlines"
        spec["problem_and_vision"]["motivation"] = "Founder pain"
        # success_metrics is [] (optional, but still required for completion)

        assert not flow.is_section_complete(spec, "problem_and_vision"), (
            "Section must not complete while optional list field 'success_metrics' is []"
        )

    def test_section_completes_when_all_fields_have_real_values(self):
        """Section completes once every field holds a real value."""
        spec = initial_spec()
        spec["problem_and_vision"]["one_liner"] = "A task app"
        spec["problem_and_vision"]["problem_statement"] = "Teams lose track"
        spec["problem_and_vision"]["business_goals"] = "Reduce missed deadlines"
        spec["problem_and_vision"]["motivation"] = "Founder pain"
        spec["problem_and_vision"]["success_metrics"] = ["30% fewer missed deadlines"]

        assert flow.is_section_complete(spec, "problem_and_vision")

    def test_section_completes_when_optional_fields_are_sentineled(self):
        """Explicit 'unspecified' / ['unspecified'] sentinels count as filled."""
        spec = initial_spec()
        spec["problem_and_vision"]["one_liner"] = "A task app"
        spec["problem_and_vision"]["problem_statement"] = "Teams lose track"
        spec["problem_and_vision"]["business_goals"] = "Reduce missed deadlines"
        spec["problem_and_vision"]["motivation"] = "unspecified"
        spec["problem_and_vision"]["success_metrics"] = ["unspecified"]

        assert flow.is_section_complete(spec, "problem_and_vision"), (
            "Explicit sentinels on optional fields must satisfy the completion rule"
        )

    def test_empty_list_is_not_filled(self):
        """[] means 'not yet asked' — it must not satisfy the completion check."""
        spec = initial_spec()
        spec["users_and_use_cases"]["target_users"] = "Remote teams"
        spec["users_and_use_cases"]["primary_use_cases"] = ["Task tracking"]
        # user_personas = [] — never asked

        assert not flow.is_section_complete(spec, "users_and_use_cases"), (
            "[] (not-yet-asked) must not be treated as filled"
        )

    def test_all_sections_checked_for_completion(self):
        """all_sections_complete returns False until every section is filled."""
        spec = initial_spec()
        # Only fill problem_and_vision
        spec["problem_and_vision"]["one_liner"] = "A task app"
        spec["problem_and_vision"]["problem_statement"] = "Teams lose track"
        spec["problem_and_vision"]["business_goals"] = "Reduce missed deadlines"
        spec["problem_and_vision"]["motivation"] = "Founder pain"
        spec["problem_and_vision"]["success_metrics"] = ["30% fewer missed deadlines"]

        assert not flow.all_sections_complete(spec), (
            "all_sections_complete must be False while any section has empty fields"
        )


# ── Bug 2: Shape bleed ───────────────────────────────────────────────────────
#
# The model sometimes copies the mvp_features object shape ({name, priority})
# into plain list fields like future_features or integrations. The normalizer
# must only touch mvp_features and known_risks — never other list fields.

class TestShapeBleed:

    def test_normalize_does_not_touch_future_features(self):
        """normalize_structured_fields must leave future_features untouched."""
        spec = initial_spec()
        spec["scope_and_features"]["future_features"] = [
            {"name": "Time tracking", "priority": "P1"},  # wrong shape from model
        ]
        original = copy.deepcopy(spec["scope_and_features"]["future_features"])

        flow.normalize_structured_fields(spec)

        assert spec["scope_and_features"]["future_features"] == original, (
            "future_features must not be transformed by normalize_structured_fields"
        )

    def test_normalize_does_not_touch_integrations(self):
        """normalize_structured_fields must leave integrations untouched."""
        spec = initial_spec()
        spec["technical_requirements"]["integrations"] = [
            {"name": "Slack", "type": "webhook"},  # wrong shape from model
        ]
        original = copy.deepcopy(spec["technical_requirements"]["integrations"])

        flow.normalize_structured_fields(spec)

        assert spec["technical_requirements"]["integrations"] == original

    def test_normalize_does_not_touch_user_personas(self):
        """normalize_structured_fields must leave user_personas untouched."""
        spec = initial_spec()
        spec["users_and_use_cases"]["user_personas"] = [
            {"name": "Team lead", "role": "manager"},  # wrong shape from model
        ]
        original = copy.deepcopy(spec["users_and_use_cases"]["user_personas"])

        flow.normalize_structured_fields(spec)

        assert spec["users_and_use_cases"]["user_personas"] == original

    def test_normalize_does_fix_mvp_features(self):
        """Sanity: normalize_structured_fields DOES coerce mvp_features entries."""
        spec = initial_spec()
        spec["scope_and_features"]["mvp_features"] = [
            "User login",            # plain string → gets priority P1
            {"name": "Dashboard"},   # dict missing priority → defaults to P1
        ]

        flow.normalize_structured_fields(spec)
        feats = spec["scope_and_features"]["mvp_features"]

        assert feats[0] == {"name": "User login", "priority": "P1"}
        assert feats[1] == {"name": "Dashboard", "priority": "P1"}
        assert all(set(f.keys()) == {"name", "priority"} for f in feats)

    def test_normalize_does_fix_known_risks(self):
        """Sanity: normalize_structured_fields DOES coerce known_risks entries."""
        spec = initial_spec()
        spec["risks_assumptions"]["known_risks"] = [
            "Low adoption",  # plain string → gets impact Medium, mitigation unspecified
        ]

        flow.normalize_structured_fields(spec)
        risks = spec["risks_assumptions"]["known_risks"]

        assert risks[0] == {
            "risk": "Low adoption",
            "impact": "Medium",
            "mitigation": "unspecified",
        }
        assert set(risks[0].keys()) == {"risk", "impact", "mitigation"}


# ── Bug 3: Bulk sentinel fabrication ─────────────────────────────────────────
#
# The model bulk-filled future sections with 'unspecified' to appear complete,
# skipping questions the user was never asked. process_turn must strip these.

class TestBulkSentinelFabrication:

    def test_process_turn_strips_string_sentinel_from_future_section(self):
        """Fabricated 'unspecified' on a future string field is reverted to None."""
        prev_spec = initial_spec()  # current_section = problem_and_vision
        model_output = {
            "problem_and_vision": {
                "one_liner": "A task app",
            },
            "users_and_use_cases": {
                "target_users": "unspecified",  # model fabricated this
            },
        }

        result = flow.process_turn(prev_spec, model_output, "A task app for teams")

        assert result["users_and_use_cases"]["target_users"] is None, (
            "Fabricated string sentinel in future section must be reverted to None"
        )

    def test_process_turn_strips_list_sentinel_from_future_section(self):
        """Fabricated ['unspecified'] on a future list field is reverted to []."""
        prev_spec = initial_spec()
        model_output = {
            "problem_and_vision": {"one_liner": "A task app"},
            "users_and_use_cases": {
                "primary_use_cases": ["unspecified"],  # fabricated
            },
        }

        result = flow.process_turn(prev_spec, model_output, "A task app for teams")

        assert result["users_and_use_cases"]["primary_use_cases"] == [], (
            "Fabricated list sentinel in future section must be reverted to []"
        )

    def test_process_turn_strips_sentinels_across_multiple_future_sections(self):
        """Sentinels fabricated across several future sections are all cleared."""
        prev_spec = initial_spec()
        model_output = {
            "problem_and_vision": {
                "one_liner": "A task app",
                "problem_statement": "Teams lose track",
                "business_goals": "Reduce missed deadlines",
                "motivation": "unspecified",        # current section — allowed
                "success_metrics": ["unspecified"],  # current section — allowed
            },
            "users_and_use_cases": {
                "target_users": "unspecified",          # fabricated
                "primary_use_cases": ["unspecified"],   # fabricated
                "user_personas": ["unspecified"],        # fabricated
            },
            "scope_and_features": {
                "mvp_features": ["unspecified"],         # fabricated
                "future_features": ["unspecified"],      # fabricated
                "explicitly_out_of_scope": ["unspecified"],  # fabricated
            },
        }

        result = flow.process_turn(prev_spec, model_output, "A comprehensive task app")

        # Current-section sentinels must be kept
        assert result["problem_and_vision"]["motivation"] == "unspecified"
        assert result["problem_and_vision"]["success_metrics"] == ["unspecified"]

        # Future-section fabrications must be cleared
        assert result["users_and_use_cases"]["target_users"] is None
        assert result["users_and_use_cases"]["primary_use_cases"] == []
        assert result["users_and_use_cases"]["user_personas"] == []
        assert result["scope_and_features"]["mvp_features"] == []
        assert result["scope_and_features"]["future_features"] == []
        assert result["scope_and_features"]["explicitly_out_of_scope"] == []

    def test_process_turn_preserves_real_values_in_future_sections(self):
        """Real values volunteered for future sections must NOT be stripped."""
        prev_spec = initial_spec()
        model_output = {
            "problem_and_vision": {"one_liner": "A task app"},
            "users_and_use_cases": {
                "target_users": "Remote software teams",  # real value, not a sentinel
            },
        }

        result = flow.process_turn(prev_spec, model_output, "A task app for remote software teams")

        assert result["users_and_use_cases"]["target_users"] == "Remote software teams", (
            "Real values in future sections must be preserved — only sentinels rejected"
        )


# ── Bug 4: Priority misgrouping in PRD preparation ───────────────────────────
#
# _prepare_spec_for_prd pre-groups mvp_features into P0/P1/P2 bucket keys.
# If features land in the wrong bucket, the PRD's Must-have/Should-have/
# Could-have subsections are wrong.

def _parse_prd_scope(spec: dict) -> dict:
    """Run _prepare_spec_for_prd and return the scope_and_features dict."""
    raw = _prepare_spec_for_prd(spec)
    json_start = raw.index("{")
    return json.loads(raw[json_start:])["scope_and_features"]


class TestPrdPriorityGrouping:

    def test_p0_features_land_in_must_have_bucket(self, complete_spec):
        complete_spec["scope_and_features"]["mvp_features"] = [
            {"name": "Auth", "priority": "P0"},
            {"name": "Export", "priority": "P0"},
        ]
        scope = _parse_prd_scope(complete_spec)

        assert scope["mvp_features_must_have_P0"] == ["Auth", "Export"]
        assert scope["mvp_features_should_have_P1"] == []
        assert scope["mvp_features_could_have_P2"] == []

    def test_p1_features_land_in_should_have_bucket(self, complete_spec):
        complete_spec["scope_and_features"]["mvp_features"] = [
            {"name": "Dashboard", "priority": "P1"},
        ]
        scope = _parse_prd_scope(complete_spec)

        assert scope["mvp_features_should_have_P1"] == ["Dashboard"]
        assert "Dashboard" not in scope["mvp_features_must_have_P0"]
        assert "Dashboard" not in scope["mvp_features_could_have_P2"]

    def test_p2_features_land_in_could_have_bucket(self, complete_spec):
        complete_spec["scope_and_features"]["mvp_features"] = [
            {"name": "Dark mode", "priority": "P2"},
        ]
        scope = _parse_prd_scope(complete_spec)

        assert scope["mvp_features_could_have_P2"] == ["Dark mode"]
        assert "Dark mode" not in scope["mvp_features_must_have_P0"]
        assert "Dark mode" not in scope["mvp_features_should_have_P1"]

    def test_mixed_priorities_sorted_into_correct_buckets(self, complete_spec):
        complete_spec["scope_and_features"]["mvp_features"] = [
            {"name": "Auth", "priority": "P0"},
            {"name": "Dashboard", "priority": "P1"},
            {"name": "Dark mode", "priority": "P2"},
            {"name": "Export", "priority": "P0"},
        ]
        scope = _parse_prd_scope(complete_spec)

        assert scope["mvp_features_must_have_P0"] == ["Auth", "Export"]
        assert scope["mvp_features_should_have_P1"] == ["Dashboard"]
        assert scope["mvp_features_could_have_P2"] == ["Dark mode"]

    def test_all_three_bucket_keys_always_present(self, complete_spec):
        """All three keys must exist even when some buckets are empty."""
        complete_spec["scope_and_features"]["mvp_features"] = [
            {"name": "Auth", "priority": "P0"},
        ]
        scope = _parse_prd_scope(complete_spec)

        assert "mvp_features_must_have_P0" in scope
        assert "mvp_features_should_have_P1" in scope
        assert "mvp_features_could_have_P2" in scope

    def test_structured_field_edit_via_process_turn(self, complete_spec):
        """Migrated from verify_m4.py: process_turn correctly updates priority
        and risk mitigation without corrupting object shape or flipping phase."""
        prev_spec = complete_spec
        model_output = {
            "scope_and_features": {
                "mvp_features": [
                    {"name": "User authentication", "priority": "P0"},
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

        updated = flow.process_turn(prev_spec, model_output, "Actually auth should be P0")

        feats = updated["scope_and_features"]["mvp_features"]
        auth = next(f for f in feats if f["name"] == "User authentication")
        assert auth["priority"] == "P0"
        assert set(auth.keys()) == {"name", "priority"}

        risk = updated["risks_assumptions"]["known_risks"][0]
        assert risk["mitigation"] == "Run a 30-day beta with 5 teams before public launch"
        assert risk["impact"] == "High"
        assert set(risk.keys()) == {"risk", "impact", "mitigation"}

        assert updated["_meta"]["phase"] == "ready_for_prd", (
            "Phase must stay ready_for_prd — all fields are still filled after the edit"
        )
