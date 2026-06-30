"""The project-specification schema — single source of truth in code.

`INITIAL_SPEC` is copied verbatim from docs/intake-chatbot-prompts.md (the
"Shared spec schema" section). Per project convention, that document is the
source of truth; this literal must stay in sync with it. Both the per-turn
Prompt A system prompt and any future Prompt B inject the same schema so they
can never drift.

`deep_merge` overlays the model's `updated_spec` onto the previous spec so that
if the model ever omits a section or field, the prior value is preserved rather
than disappearing (the "merge it back in from the previous spec" safeguard).
"""

import copy
from typing import Any


def initial_spec() -> dict[str, Any]:
    """Return a fresh deep copy of the starting spec for a new session."""
    return copy.deepcopy(_INITIAL_SPEC)


# Verbatim from docs/intake-chatbot-prompts.md — do not edit field names or
# shapes here without updating that document first.
_INITIAL_SPEC: dict[str, Any] = {
    "problem_and_vision": {
        "one_liner": None,
        "problem_statement": None,
        "business_goals": None,
        "motivation": None,
        "success_metrics": [],
    },
    "users_and_use_cases": {
        "target_users": None,
        "primary_use_cases": [],
        "user_personas": [],
    },
    "scope_and_features": {
        "mvp_features": [],
        "future_features": [],
        "explicitly_out_of_scope": [],
    },
    "technical_requirements": {
        "tech_stack_preference": None,
        "integrations": [],
        "data_model": None,
        "non_functional_requirements": [],
        "compliance_requirements": [],
    },
    "ux_design": {
        "platform": None,
        "design_preferences": None,
        "accessibility_needs": None,
    },
    "deployment_infra": {
        "deployment_target": None,
        "environments": None,
        "cicd_needs": None,
    },
    "timeline_resources": {
        "timeline": None,
        "budget": None,
        "team_size_roles": None,
    },
    "maintenance_ops": {
        "maintenance_plan": None,
        "monitoring_logging": None,
        "support_plan": None,
    },
    "risks_assumptions": {
        "known_risks": [],
        "assumptions": [],
        "dependencies": [],
    },
    "_meta": {
        "current_section": "problem_and_vision",
        "completed_sections": [],
        "questions_asked_this_section": 0,
        "phase": "gathering",
    },
}


def _is_empty(value: Any) -> bool:
    """True for the schema's 'not yet filled' values: null, "", or []."""
    return value is None or value == "" or value == []


def deep_merge(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Recursively overlay `new` onto a deep copy of `old`.

    Dicts are merged key-by-key. Keys present in `old` but absent from `new`
    are preserved — this stops a model that forgets to echo a section from
    wiping it out.

    Crucially, an already-filled field is never regressed to an empty value: if
    `new` carries null / "" / [] for a key that `old` already has a real value
    for, the old value is kept. In this forward-only intake flow a field never
    legitimately goes back to empty, so an empty value from the model is always
    an extraction slip, not an intentional clear. (A real value or an explicit
    "unspecified" / ["unspecified"] sentinel still overwrites freely.)
    """
    merged = copy.deepcopy(old)
    for key, new_value in new.items():
        old_value = merged.get(key)
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            merged[key] = deep_merge(old_value, new_value)
        elif _is_empty(new_value) and not _is_empty(old_value):
            # Don't let the model blank out a field it previously filled.
            continue
        else:
            merged[key] = copy.deepcopy(new_value)
    return merged
