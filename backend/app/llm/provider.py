"""LLM provider router — the single seam for dev/prod swaps.

Every caller goes through `generate(messages, system_prompt)` and never imports
a concrete provider directly. Switching from Ollama (dev) to a cloud API (prod,
Milestone 5) is then an env-var change (LLM_PROVIDER), never a code change.

Per project convention, any provider API key is read here server-side only and
is never exposed to the frontend.
"""

import os

from app.schemas import Message
from app.llm import ollama_client


async def generate(
    messages: list[Message],
    system_prompt: str,
    *,
    format: str | None = None,
    temperature: float | None = None,
) -> str:
    """Generate an assistant reply from conversation messages + a system prompt.

    Dispatches on the LLM_PROVIDER env var. Only "ollama" is implemented in
    Milestone 1; cloud providers are added behind this same signature later.

    Optional `format`/`temperature` are passed through to the provider — e.g.
    format="json" to constrain the model to valid JSON for the Prompt A turn.
    """
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()

    if provider == "ollama":
        return await ollama_client.generate(
            messages, system_prompt, format=format, temperature=temperature
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. "
        "Milestone 1 supports only 'ollama'."
    )
