"""LLM call function shaped like ai-system's llm_core.py.

Signature matches the reference's llm_call_async(url, model, messages,
headers=None) exactly, plus two additions confirmed with the project owner:
keyword-only `temperature` and `num_predict` params (the reference has
`temperature` too, under the same name). `num_predict` was added after M8
found that Prompt B's PRD generation intermittently truncates mid-document
on the local 3B model — capping it explicitly at a generous ceiling rules out
Ollama's server-side default (context-window-limited, effectively unbounded
for a short prompt) as a variable. The reference has no `format`/JSON-mode
param — it doesn't use Ollama's native JSON mode either, relying on prompt
instructions alone — so this doesn't add one.

Only the signature/shape needs to match the reference; the body is a plain
Ollama /api/chat call so swapping in a different backend later is a
same-signature implementation swap, not a rewrite.
"""

import os

import httpx

_TIMEOUT = httpx.Timeout(float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300")))


async def llm_call_async(
    url: str,
    model: str,
    messages: list[dict],
    headers: dict | None = None,
    *,
    temperature: float | None = None,
    num_predict: int | None = None,
) -> str:
    """POST messages to an Ollama-compatible /api/chat endpoint, return the reply text."""
    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    options: dict = {}
    if temperature is not None:
        options["temperature"] = temperature
    if num_predict is not None:
        options["num_predict"] = num_predict
    if options:
        payload["options"] = options

    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=req_headers)
        resp.raise_for_status()
        data = resp.json()

    return data["message"]["content"]
