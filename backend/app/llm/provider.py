"""LLM provider router — the single seam for dev/prod swaps.

Every caller goes through `generate(messages, system_prompt)` and never imports
a concrete provider directly. Switching providers is an env-var change
(LLM_PROVIDER), never a code change.

Supported values:
  ollama  — local Ollama server (default, dev)
  openai  — any OpenAI-compatible /v1/chat/completions endpoint (prod)

Per project convention, any provider API key is read server-side only and is
never exposed to the frontend.
"""

import os

from app.schemas import Message
from app.llm import ollama_client, openai_client


async def generate(
    messages: list[Message],
    system_prompt: str,
    *,
    format: str | None = None,
    temperature: float | None = None,
) -> str:
    """Generate an assistant reply from conversation messages + a system prompt.

    Dispatches on LLM_PROVIDER. Optional format/temperature are passed through
    to whichever client handles the request.
    """
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()

    if provider == "ollama":
        return await ollama_client.generate(
            messages, system_prompt, format=format, temperature=temperature
        )

    if provider == "openai":
        return await openai_client.generate(
            messages, system_prompt, format=format, temperature=temperature
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. Supported values: 'ollama', 'openai'."
    )
