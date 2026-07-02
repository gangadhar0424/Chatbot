"""Auth dependency stub, shaped like ai-system's require_user(request) -> str.

Same call shape as the real thing (Depends(require_user) usable in any route),
so every handler already expects an owner string. No real auth logic yet —
always resolves to the same fixed user.
"""

from fastapi import Request

_STUB_USER = "dev-user"


def require_user(request: Request) -> str:
    """FastAPI dependency: returns the resolved username. Stub — always dev-user."""
    return _STUB_USER
