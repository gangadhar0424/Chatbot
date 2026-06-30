"""Ollama-backed implementation of the provider `generate()` interface.

Talks to a locally running Ollama server's /api/chat endpoint. The model is
env-configurable (OLLAMA_MODEL) with no in-code default — if it's unset we fail
fast with a clear message rather than silently calling a model that isn't pulled.
"""

import os

import httpx

# Generous timeout: a cold model load plus a full spec-JSON turn (Prompt A
# re-emits the entire spec object each turn) can run well past two minutes on a
# small local model. Configurable via OLLAMA_TIMEOUT_SECONDS.
_REQUEST_TIMEOUT = httpx.Timeout(float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300")))


def _base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")


def _model() -> str:
    model = os.getenv("OLLAMA_MODEL")
    if not model:
        raise RuntimeError(
            "OLLAMA_MODEL is not set. Pull a model (e.g. `ollama pull llama3.1`) "
            "and set OLLAMA_MODEL to its name. See backend/.env.example."
        )
    return model


async def generate(
    messages,
    system_prompt: str,
    *,
    format: str | None = None,
    temperature: float | None = None,
) -> str:
    """POST the conversation to Ollama and return the assistant's reply text.

    Optional `format` maps to Ollama's structured-output constraint (pass
    "json" to force valid JSON, as Prompt A requires). Optional `temperature`
    is sent under Ollama's `options` block. Both default to off so callers that
    don't need them get the plain Milestone 1 behaviour.
    """
    payload_messages = [{"role": "system", "content": system_prompt}]
    payload_messages += [{"role": m.role, "content": m.content} for m in messages]

    payload = {
        "model": _model(),
        "messages": payload_messages,
        "stream": False,
    }
    if format is not None:
        payload["format"] = format
    if temperature is not None:
        payload["options"] = {"temperature": temperature}

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        resp = await client.post(f"{_base_url()}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

    return data["message"]["content"]
