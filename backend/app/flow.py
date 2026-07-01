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
import re
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


# --- Grounding check (M8.1) ------------------------------------------------

_GROUNDING_STOPS: frozenset[str] = frozenset({
    "the", "and", "for", "are", "not", "but", "with", "this", "that",
    "have", "from", "its", "into", "was", "were", "been", "being",
    "has", "had", "did", "does", "will", "would", "could", "should",
    "may", "might", "shall", "can", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "than", "too",
    "very", "just", "only", "also", "same", "then", "here", "there",
    "when", "where", "which", "who", "how", "what", "your", "our",
    "their", "they", "them", "these", "those", "you", "her", "his",
    "its", "out", "about", "above", "after", "before", "between",
    "during", "through", "without", "within", "want", "like", "use",
    "make", "need", "know", "get", "see", "one", "two", "new", "now",
})


def _grounding_tokens(text: str) -> set[str]:
    """Lower-cased alpha tokens ≥ 3 chars, with stop-words excluded."""
    return {
        w for w in re.findall(r"[a-z]{3,}", text.lower())
        if w not in _GROUNDING_STOPS
    }


def _field_text(value: Any) -> str:
    """Extract the human-readable text from a field value for token comparison.

    For structured list fields (mvp_features / known_risks entries), only the
    text components are relevant — priority, impact, and mitigation are model
    inferences that the semantic validator handles separately.
    """
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(item.get("name") or item.get("risk") or "")
            else:
                parts.append(str(item))
        return " ".join(parts)
    if isinstance(value, dict):
        return value.get("name") or value.get("risk") or ""
    return str(value)


def _grounding_confidence(value: Any, msg_tokens: set[str]) -> float:
    """Keyword-overlap confidence: fraction of value tokens found in msg_tokens.

    Returns 0.0–1.0.  A value with no significant tokens (e.g. a number)
    scores 1.0 to avoid false reverts on trivially short values.
    """
    value_tokens = _grounding_tokens(_field_text(value))
    if not value_tokens:
        return 1.0
    return len(value_tokens & msg_tokens) / len(value_tokens)


def check_grounding(
    spec: dict,
    prev_spec: dict,
    user_message: str,
    *,
    _report: dict | None = None,
) -> list[str]:
    """Revert newly-filled fields whose values can't be traced to the user message.

    'Newly filled' means the field was empty in prev_spec and now holds a real
    (non-sentinel, non-empty) value.  A value is grounded if at least one
    significant token from the extracted value also appears in the user message
    (keyword-overlap with stop-word filtering).  Sentinels are always accepted.

    _report, if provided, is populated with per-field grounding metadata for
    the confidence logger:  {field_path: {extracted_value, confidence, grounded, reverted}}.

    Returns a list of reverted 'section.field' paths for logging.
    Mutates spec in place.
    """
    msg_tokens = _grounding_tokens(user_message)
    reverted: list[str] = []

    for section in SECTION_ORDER:
        for field in SECTION_FIELDS[section]:
            prev_val = prev_spec[section][field]
            new_val = spec[section][field]

            if not _is_empty(prev_val):
                continue  # already filled in prev — trust it
            if _is_empty(new_val):
                continue  # still empty — nothing to check
            if _is_sentinel(new_val):
                continue  # explicit skip is always legitimate

            confidence = _grounding_confidence(new_val, msg_tokens)
            grounded = confidence > 0.0
            field_path = f"{section}.{field}"

            if _report is not None:
                _report[field_path] = {
                    "extracted_value": new_val,
                    "confidence": confidence,
                    "grounded": grounded,
                    "reverted": not grounded,
                }

            if not grounded:
                spec[section][field] = copy.deepcopy(prev_val)
                reverted.append(field_path)

    return reverted


# --- Semantic validation (M8.2) --------------------------------------------

# P0 signals: explicit "must-have" language.  The literal "p0" is included so
# a user who types "auth should be P0" is treated as an explicit P0 signal.
_P0_SIGNALS: frozenset[str] = frozenset({
    "must", "need", "needs", "essential", "critical", "required", "require",
    "requires", "absolutely", "definitely", "necessary", "mandatory",
    "launch", "blocker", "blocking", "p0",
})

_BOILERPLATE_MIN_TOKENS = 4


def validate_semantic(
    spec: dict,
    prev_spec: dict,
    history_text: str,
) -> list[str]:
    """Semantic checks that go beyond shape validation.

    A. Priority inflation guard: a newly-extracted P0 mvp_features entry is
       only accepted when the full conversation history (joined) contains at
       least one explicit must-have signal word.  Without such evidence the
       priority is downgraded to 'P1' (the model's instructed default for
       ambiguous cases).

       'Newly extracted' = the whole mvp_features field was empty in prev_spec
       and now has entries.  Edits to an already-filled field are not re-checked
       (the user deliberately changed the priority).

    B. Boilerplate mitigation guard: a mitigation string that has fewer than
       _BOILERPLATE_MIN_TOKENS substantive tokens is treated as generic
       boilerplate.  The mitigation key is reset to 'unspecified' so the PRD
       flags it as an open question rather than silently printing "TBD".

       Same 'newly extracted' rule: only fires when known_risks was [] before.

    Returns a list of corrected paths for logging.  Mutates spec in place.
    """
    full_text_tokens = _grounding_tokens(history_text)
    has_p0_signal = bool(full_text_tokens & _P0_SIGNALS)
    corrected: list[str] = []

    # A. Priority inflation guard
    prev_feats = prev_spec["scope_and_features"]["mvp_features"]
    new_feats = spec["scope_and_features"]["mvp_features"]
    if (
        _is_empty(prev_feats)
        and isinstance(new_feats, list)
        and new_feats not in ([], [UNSPECIFIED])
        and not has_p0_signal
    ):
        for feat in new_feats:
            if isinstance(feat, dict) and feat.get("priority") == "P0":
                feat["priority"] = "P1"
                corrected.append(
                    f"scope_and_features.mvp_features[{feat.get('name', '?')}].priority"
                )

    # B. Boilerplate mitigation guard
    prev_risks = prev_spec["risks_assumptions"]["known_risks"]
    new_risks = spec["risks_assumptions"]["known_risks"]
    if (
        _is_empty(prev_risks)
        and isinstance(new_risks, list)
        and new_risks not in ([], [UNSPECIFIED])
    ):
        for risk in new_risks:
            if not isinstance(risk, dict):
                continue
            mitigation = risk.get("mitigation", UNSPECIFIED)
            if mitigation == UNSPECIFIED:
                continue
            if len(_grounding_tokens(mitigation)) < _BOILERPLATE_MIN_TOKENS:
                risk["mitigation"] = UNSPECIFIED
                corrected.append(
                    f"risks_assumptions.known_risks[{risk.get('risk', '?')}].mitigation"
                )

    return corrected


def process_turn(
    prev_spec: dict,
    updated_spec: Any,
    user_message: str,
    *,
    history: list | None = None,
    _enable_grounding: bool = True,
    _grounding_report: dict | None = None,
) -> dict:
    """Apply one turn's model output to the spec under full backend control.

    Pipeline:
      1. deep_merge — overlay model extraction onto prev_spec
      2. reject_future_sentinels — drop fabricated future-section sentinels
      3. apply_skip — deterministic sentinel for the skip button
      4. check_grounding (M8.1) — revert newly-filled fields not traceable
         to the user's message; populates _grounding_report when provided
      5. normalize_structured_fields — coerce object shapes, backfill defaults
      6. normalize_sentinel_shapes — fix list-vs-string sentinel mismatches
      7. validate_semantic (M8.2) — priority inflation + boilerplate mitigation
      8. recompute_meta — authoritative current_section / phase

    history is a list of Message objects for the full conversation so far
    (used by validate_semantic's priority inflation guard, which must scan the
    entire conversation — the P0 signal often appears turns before the feature
    is formally extracted).

    _enable_grounding=False disables checks 4 and 7 (for tests that
    intentionally drive ungrounded model output to verify downstream behavior).

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

    if _enable_grounding:
        reverted = check_grounding(
            spec, prev_spec, user_message, _report=_grounding_report
        )
        if reverted:
            import logging
            logging.getLogger(__name__).warning(
                "[grounding] reverted %d field(s): %s", len(reverted), reverted
            )

    normalize_structured_fields(spec)
    normalize_sentinel_shapes(spec)

    if _enable_grounding:
        # Build the history text for semantic validation: full conversation
        # history joined together, plus the current user message appended.
        history_parts: list[str] = []
        if history:
            history_parts = [msg.content for msg in history]
        history_parts.append(user_message)
        history_text = " ".join(history_parts)

        corrected = validate_semantic(spec, prev_spec, history_text)
        if corrected:
            import logging
            logging.getLogger(__name__).warning(
                "[semantic] corrected %d value(s): %s", len(corrected), corrected
            )

    recompute_meta(spec, prev_meta)
    return spec
