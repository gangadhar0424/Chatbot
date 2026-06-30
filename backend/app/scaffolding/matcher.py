"""Template matching logic.

Maps a free-text tech_stack_preference string to the closest template key.
Uses keyword scanning — transparent and debuggable for the short strings
the intake flow actually produces. No ML, no fuzzy scoring.

The MatchResult carries an 'exact' flag and an optional 'note'. When exact
is False the note is surfaced to the user in the generated README so they
know what was selected and why, rather than silently receiving an
unexpected skeleton.
"""

from dataclasses import dataclass


@dataclass
class MatchResult:
    template: str       # directory name under scaffolding/templates/
    exact: bool         # True only when "next" / "nextjs" keyword was present
    note: str | None    # human-readable explanation for approximate matches


_UNSPECIFIED = {"unspecified", ""}


def pick_template(tech_stack_preference: str | None) -> MatchResult:
    """Return the best-matching template for the given stack string."""
    if (
        not tech_stack_preference
        or tech_stack_preference.strip().lower() in _UNSPECIFIED
    ):
        return MatchResult(
            template="generic",
            exact=False,
            note="No stack specified — using a minimal generic structure.",
        )

    s = tech_stack_preference.lower()

    has_next    = any(kw in s for kw in ("nextjs", "next.js", "next "))
    has_react   = "react" in s
    has_fastapi = any(kw in s for kw in ("fastapi", "fast api"))
    has_python  = "python" in s
    has_node    = any(kw in s for kw in ("node", "express"))

    # ── Exact matches (Next.js keyword present) ──────────────────────────────
    if has_next and (has_fastapi or has_python):
        return MatchResult(template="nextjs-fastapi", exact=True, note=None)

    if has_next and has_node:
        return MatchResult(template="nextjs-node", exact=True, note=None)

    # ── Approximate matches (React mentioned but not explicitly Next.js) ─────
    if has_react and (has_fastapi or has_python):
        return MatchResult(
            template="nextjs-fastapi",
            exact=False,
            note=(
                "Scaffolded as Next.js (closest match to your React + FastAPI "
                "preference — Next.js is a React framework and the project "
                "structure is identical)."
            ),
        )

    if has_react and has_node:
        return MatchResult(
            template="nextjs-node",
            exact=False,
            note=(
                "Scaffolded as Next.js (closest match to your React + Node "
                "preference — Next.js is a React framework)."
            ),
        )

    # ── Nothing matched well enough ──────────────────────────────────────────
    return MatchResult(
        template="generic",
        exact=False,
        note=(
            f"Stack '{tech_stack_preference}' did not match any template — "
            "using a minimal generic structure rather than guessing."
        ),
    )
