"""Backend-authoritative flow control for the intake conversation.

Prompt A (the model) handles extraction and question phrasing. But on a small
local model its _meta bookkeeping and phase signal proved unreliable in the
Milestone 2 verification — it marked sections complete out of order and emitted
structured fields in the wrong shape. So per the design doc's practical notes
("walk updated_spec yourself", "backfill a default in code", "don't trust the
model's phase"), the BACKEND is the source of truth for:

  - which section is current and which are complete (recompute_meta)
  - the object shapes of the structured fields (normalize_structured_fields)
  - whether the conversation is truly ready_for_prd (the phase gate)

Section order and the field list per section are derived from the schema in
app.spec, so they can never drift from the source of truth.
"""

import copy
from typing import Any

from app.spec import deep_merge, initial_spec, _is_empty

# Derive section order and each section's fields from the schema itself.
_TEMPLATE = initial_spec()
SECTION_ORDER: list[str] = [k for k in _TEMPLATE if k != "_meta"]
SECTION_FIELDS: dict[str, list[str]] = {
    section: list(_TEMPLATE[section].keys()) for section in SECTION_ORDER
}

VALID_PRIORITIES = {"P0", "P1", "P2"}
VALID_IMPACTS = {"High", "Medium", "Low"}
UNSPECIFIED = "unspecified"

# The canned message the frontend "Not sure / skip" button sends. Kept in sync
# with SKIP_MESSAGE in frontend/app/page.tsx.
SKIP_MESSAGE = "I'm not sure, let's move on."


def is_filled(value: Any) -> bool:
    """A field is filled if it holds a real value OR an explicit sentinel.

    "unspecified" (a non-empty string) and ["unspecified"] (a non-empty list)
    both count as filled — they mean "asked, user chose not to specify," which
    is different from null / [] meaning "not yet asked."
    """
    return not _is_empty(value)


def is_section_complete(spec: dict, section: str) -> bool:
    """A section is complete only when every field it contains is filled."""
    return all(is_filled(spec[section][field]) for field in SECTION_FIELDS[section])


def all_sections_complete(spec: dict) -> bool:
    """The backend-side completion check: every field in every section filled."""
    return all(is_section_complete(spec, section) for section in SECTION_ORDER)


def _sentinel_for(section: str, field: str) -> Any:
    """The right sentinel shape for a field: ["unspecified"] for list fields,
    "unspecified" for single-value fields — decided by the schema template."""
    return ["unspecified"] if isinstance(_TEMPLATE[section][field], list) else UNSPECIFIED


def apply_skip(spec: dict, section: str) -> str | None:
    """Record an explicit "unspecified" for the first still-empty field of
    `section`, deterministically — so the skip button works even when the model
    ignores the user's "move on." Returns the field name skipped, or None if the
    section is already fully filled. Mutates spec in place.

    First-empty in schema order matches Prompt A's required-fields-first asking,
    so this lands on the field the user was most likely just asked about.
    """
    for field in SECTION_FIELDS[section]:
        if not is_filled(spec[section][field]):
            spec[section][field] = _sentinel_for(section, field)
            return field
    return None


def missing_fields(spec: dict) -> list[str]:
    """List "section.field" for every still-empty field — for debugging."""
    out: list[str] = []
    for section in SECTION_ORDER:
        for field in SECTION_FIELDS[section]:
            if not is_filled(spec[section][field]):
                out.append(f"{section}.{field}")
    return out


# --- Structured-field normalization ----------------------------------------


def _normalize_feature(feature: Any) -> dict:
    """Coerce one mvp_features entry into {"name", "priority"} with a P1 default."""
    if isinstance(feature, dict):
        name = feature.get("name") or feature.get("feature") or ""
        priority = feature.get("priority", "P1")
    elif isinstance(feature, str):
        name, priority = feature, "P1"
    else:
        name, priority = str(feature), "P1"
    if priority not in VALID_PRIORITIES:
        priority = "P1"
    return {"name": name, "priority": priority}


def _normalize_risk(risk: Any) -> dict:
    """Coerce one known_risks entry into {"risk", "impact", "mitigation"}."""
    if isinstance(risk, dict):
        description = risk.get("risk") or risk.get("description") or ""
        impact = risk.get("impact", "Medium")
        mitigation = risk.get("mitigation") or UNSPECIFIED
    elif isinstance(risk, str):
        description, impact, mitigation = risk, "Medium", UNSPECIFIED
    else:
        description, impact, mitigation = str(risk), "Medium", UNSPECIFIED
    if impact not in VALID_IMPACTS:
        impact = "Medium"
    return {"risk": description, "impact": impact, "mitigation": mitigation}


def normalize_structured_fields(spec: dict) -> None:
    """Force mvp_features and known_risks into their required object shapes.

    Backfills defaults in code (priority P1; impact Medium; mitigation
    "unspecified") rather than bouncing a question back to the user they
    already effectively answered. The whole-field ["unspecified"] sentinel and
    the not-yet-asked [] are left untouched. Mutates spec in place.
    """
    feats = spec["scope_and_features"]["mvp_features"]
    if isinstance(feats, list) and feats not in ([], [UNSPECIFIED]):
        spec["scope_and_features"]["mvp_features"] = [
            _normalize_feature(f) for f in feats
        ]

    risks = spec["risks_assumptions"]["known_risks"]
    if isinstance(risks, list) and risks not in ([], [UNSPECIFIED]):
        spec["risks_assumptions"]["known_risks"] = [
            _normalize_risk(r) for r in risks
        ]


# --- Authoritative _meta ----------------------------------------------------


def recompute_meta(spec: dict, prev_meta: dict) -> None:
    """Recompute _meta from the actual spec contents, overriding the model.

    current_section = the first section (in order) that isn't complete; every
    section before it is complete. phase flips to "ready_for_prd" only when the
    backend confirms every field is filled — never on the model's say-so.
    Mutates spec["_meta"] in place.
    """
    completed: list[str] = []
    current: str | None = None
    for section in SECTION_ORDER:
        if is_section_complete(spec, section):
            completed.append(section)
        else:
            current = section
            break

    if current is None:
        phase = "ready_for_prd"
        current = SECTION_ORDER[-1]
    else:
        phase = "gathering"

    # questions_asked_this_section is telemetry only: increment while we stay in
    # the same section, reset to 0 when the section advances.
    if current == prev_meta.get("current_section"):
        questions = prev_meta.get("questions_asked_this_section", 0) + 1
    else:
        questions = 0

    spec["_meta"] = {
        "current_section": current,
        "completed_sections": completed,
        "questions_asked_this_section": questions,
        "phase": phase,
    }


# --- Sentinel shape + scope guards ------------------------------------------


def _is_sentinel(value: Any) -> bool:
    """True for either sentinel form, regardless of (possibly wrong) shape."""
    return value == UNSPECIFIED or value == [UNSPECIFIED]


def normalize_sentinel_shapes(spec: dict) -> None:
    """Make each sentinel match its field's actual type: list fields hold
    ["unspecified"], single-value fields hold "unspecified".

    Fixes the model storing a list sentinel on a string field (or vice versa).
    Only the sentinel forms are touched — real values are left alone. Mutates
    spec in place.
    """
    for section in SECTION_ORDER:
        for field in SECTION_FIELDS[section]:
            value = spec[section][field]
            wants_list = isinstance(_TEMPLATE[section][field], list)
            if wants_list and value == UNSPECIFIED:
                spec[section][field] = [UNSPECIFIED]
            elif not wants_list and value == [UNSPECIFIED]:
                spec[section][field] = UNSPECIFIED


def reject_future_sentinels(spec: dict, prev_spec: dict, current_section: str) -> None:
    """Drop sentinels the model fabricated for sections it hasn't reached yet.

    A sentinel means "asked, user chose not to specify" — only legitimate for
    the section currently being interviewed (or earlier). If the model dumps
    "unspecified" into a *later* section's field that was still empty, the user
    was never actually asked, so we revert it to empty. Real values extracted
    early (the user volunteering future-section info) are kept untouched — only
    fabricated sentinels are rejected. Mutates spec in place.
    """
    cur_idx = SECTION_ORDER.index(current_section)
    for idx, section in enumerate(SECTION_ORDER):
        if idx <= cur_idx:
            continue  # current and earlier sections: sentinels are allowed
        for field in SECTION_FIELDS[section]:
            if _is_sentinel(spec[section][field]) and _is_empty(prev_spec[section][field]):
                spec[section][field] = copy.deepcopy(prev_spec[section][field])


def process_turn(prev_spec: dict, updated_spec: Any, user_message: str) -> dict:
    """Apply one turn's model output to the spec under full backend control.

    Pipeline: merge the model's extraction forward → reject fabricated
    future-section sentinels → apply the deterministic skip if the user hit the
    button → normalize structured fields and sentinel shapes → recompute the
    authoritative _meta (current_section / completed_sections / phase).

    prev_spec is not mutated; the new spec is returned.
    """
    prev_meta = prev_spec["_meta"]
    current_section = prev_meta["current_section"]

    if isinstance(updated_spec, dict):
        spec = deep_merge(prev_spec, updated_spec)
    else:
        spec = copy.deepcopy(prev_spec)

    reject_future_sentinels(spec, prev_spec, current_section)
    if user_message.strip() == SKIP_MESSAGE:
        apply_skip(spec, current_section)
    normalize_structured_fields(spec)
    normalize_sentinel_shapes(spec)
    recompute_meta(spec, prev_meta)
    return spec
