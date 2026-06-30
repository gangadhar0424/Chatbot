"""OpenAI-compatible implementation of the provider generate() interface.

Talks to any OpenAI-compatible /v1/chat/completions endpoint. OPENAI_BASE_URL
defaults to https://api.openai.com/v1 but can point to Groq, Together, or any
other compatible host with no code change — only an env var.

The API key is read from OPENAI_API_KEY server-side only and is never sent to
or read from the frontend.
"""

import os

import httpx

from app.schemas import Message

_REQUEST_TIMEOUT = httpx.Timeout(float(os.getenv("OPENAI_TIMEOUT_SECONDS", "120")))


def _base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def _model() -> str:
    model = os.getenv("OPENAI_MODEL")
    if not model:
        raise RuntimeError(
            "OPENAI_MODEL is not set. Set it to the model you want, "
            "e.g. OPENAI_MODEL=gpt-4o-mini. See backend/.env.example."
        )
    return model


def _api_key() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to backend/.env "
            "(that file is gitignored — never commit the key)."
        )
    return key


async def generate(
    messages: list[Message],
    system_prompt: str,
    *,
    format: str | None = None,
    temperature: float | None = None,
) -> str:
    """POST to /v1/chat/completions and return the assistant reply text.

    format="json" maps to response_format={"type":"json_object"}.
    OpenAI requires the word "json" to appear in the system prompt when
    using JSON mode; Prompt A already contains "JSON object" so that
    constraint is satisfied without any prompt change.
    """
    payload_messages = [{"role": "system", "content": system_prompt}]
    payload_messages += [{"role": m.role, "content": m.content} for m in messages]

    payload: dict = {
        "model": _model(),
        "messages": payload_messages,
    }
    if format == "json":
        payload["response_format"] = {"type": "json_object"}
    if temperature is not None:
        payload["temperature"] = temperature

    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        resp = await client.post(
            f"{_base_url()}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()

    return resp.json()["choices"][0]["message"]["content"]
