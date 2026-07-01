"""Dedicated regression tests for reject_future_sentinels().

This function was the most critical fix in the project: the model was
bulk-fabricating "unspecified" sentinels for sections the user hadn't reached
yet, causing the section loop to skip questions the user was never asked.

These tests call reject_future_sentinels() directly with crafted inputs so
every meaningful case is exercised in isolation, making failures easy to pin.
"""

import copy

from app import flow
from app.spec import initial_spec


# ── Core behaviour: future sentinels are reverted ────────────────────────────

class TestFutureSentinelsReverted:

    def test_string_sentinel_in_next_section_is_reverted(self):
        """'unspecified' on a string field in the next section is reverted to None."""
        prev = initial_spec()
        spec = copy.deepcopy(prev)
        spec["users_and_use_cases"]["target_users"] = "unspecified"

        flow.reject_future_sentinels(spec, prev, "problem_and_vision")

        assert spec["users_and_use_cases"]["target_users"] is None

    def test_list_sentinel_in_next_section_is_reverted(self):
        """['unspecified'] on a list field in the next section is reverted to []."""
        prev = initial_spec()
        spec = copy.deepcopy(prev)
        spec["users_and_use_cases"]["primary_use_cases"] = ["unspecified"]

        flow.reject_future_sentinels(spec, prev, "problem_and_vision")

        assert spec["users_and_use_cases"]["primary_use_cases"] == []

    def test_sentinels_reverted_across_multiple_future_sections(self):
        """Fabricated sentinels two or more sections ahead are also cleared."""
        prev = initial_spec()
        spec = copy.deepcopy(prev)

        # Two sections ahead of problem_and_vision
        spec["scope_and_features"]["mvp_features"] = ["unspecified"]
        spec["scope_and_features"]["future_features"] = ["unspecified"]
        # Three sections ahead
        spec["technical_requirements"]["tech_stack_preference"] = "unspecified"
        spec["technical_requirements"]["integrations"] = ["unspecified"]

        flow.reject_future_sentinels(spec, prev, "problem_and_vision")

        assert spec["scope_and_features"]["mvp_features"] == []
        assert spec["scope_and_features"]["future_features"] == []
        assert spec["technical_requirements"]["tech_stack_preference"] is None
        assert spec["technical_requirements"]["integrations"] == []

    def test_both_sentinel_forms_reverted(self):
        """Both string form ('unspecified') and list form (['unspecified']) are rejected."""
        prev = initial_spec()
        spec = copy.deepcopy(prev)
        # technical_requirements has both string and list fields
        spec["technical_requirements"]["tech_stack_preference"] = "unspecified"
        spec["technical_requirements"]["integrations"] = ["unspecified"]

        flow.reject_future_sentinels(spec, prev, "problem_and_vision")

        assert spec["technical_requirements"]["tech_stack_preference"] is None
        assert spec["technical_requirements"]["integrations"] == []


# ── Preservation: real values and current/past sentinels are untouched ───────

class TestPreservation:

    def test_real_value_in_future_section_is_kept(self):
        """A real answer volunteered for a future section is preserved.

        Only fabricated sentinels are rejected — the user volunteering real
        information about a later section should not be discarded.
        """
        prev = initial_spec()
        spec = copy.deepcopy(prev)
        spec["users_and_use_cases"]["target_users"] = "Remote software teams"

        flow.reject_future_sentinels(spec, prev, "problem_and_vision")

        assert spec["users_and_use_cases"]["target_users"] == "Remote software teams"

    def test_sentinel_in_current_section_is_kept(self):
        """A sentinel in the current section is legitimate — user was asked and skipped."""
        prev = initial_spec()
        spec = copy.deepcopy(prev)
        spec["problem_and_vision"]["motivation"] = "unspecified"

        flow.reject_future_sentinels(spec, prev, "problem_and_vision")

        assert spec["problem_and_vision"]["motivation"] == "unspecified"

    def test_sentinel_in_completed_earlier_section_is_kept(self):
        """Sentinels already placed in past sections must not be disturbed."""
        prev = initial_spec()
        prev["problem_and_vision"]["motivation"] = "unspecified"
        spec = copy.deepcopy(prev)

        # Now in users_and_use_cases; problem_and_vision is completed
        flow.reject_future_sentinels(spec, prev, "users_and_use_cases")

        assert spec["problem_and_vision"]["motivation"] == "unspecified"

    def test_field_with_real_value_in_prev_not_reverted_even_if_now_sentinel(self):
        """If prev_spec already held a real value, the function leaves it alone.

        In practice deep_merge prevents a real value from being overwritten by a
        sentinel, so this scenario shouldn't arise in the normal pipeline — but
        the guard in reject_future_sentinels (checking _is_empty(prev_spec[field]))
        ensures it's a no-op here anyway.
        """
        prev = initial_spec()
        prev["users_and_use_cases"]["target_users"] = "Remote teams"
        spec = copy.deepcopy(prev)
        # Pretend the model tried to sentinel a field that already had a real value
        spec["users_and_use_cases"]["target_users"] = "unspecified"

        flow.reject_future_sentinels(spec, prev, "problem_and_vision")

        # prev field was not empty, so the guard _is_empty(prev[field]) is False
        # → not reverted
        assert spec["users_and_use_cases"]["target_users"] == "unspecified"


# ── Boundary: the current-section boundary is respected exactly ──────────────

class TestSectionBoundary:

    def test_only_sections_after_current_are_checked(self):
        """Fields at exactly the current-section boundary are not touched."""
        prev = initial_spec()
        spec = copy.deepcopy(prev)

        # Sentinel in current section (problem_and_vision)
        spec["problem_and_vision"]["motivation"] = "unspecified"
        # Sentinel one step ahead
        spec["users_and_use_cases"]["target_users"] = "unspecified"

        flow.reject_future_sentinels(spec, prev, "problem_and_vision")

        assert spec["problem_and_vision"]["motivation"] == "unspecified", (
            "Current-section sentinel must be untouched"
        )
        assert spec["users_and_use_cases"]["target_users"] is None, (
            "Next-section sentinel must be cleared"
        )

    def test_advancing_current_section_changes_what_is_allowed(self):
        """A sentinel that was 'future' from section 1 becomes 'current' from section 2."""
        prev = initial_spec()
        prev["_meta"]["current_section"] = "users_and_use_cases"
        spec = copy.deepcopy(prev)
        spec["users_and_use_cases"]["target_users"] = "unspecified"

        # Running from users_and_use_cases: sentinel in that section is allowed
        flow.reject_future_sentinels(spec, prev, "users_and_use_cases")

        assert spec["users_and_use_cases"]["target_users"] == "unspecified", (
            "Once the section is current, its sentinels are allowed"
        )
