# AI Project-Intake Chatbot

A conversational requirements-gathering assistant. It interviews a user about a
software project, fills a structured spec field-by-field, and generates a PRD.

This repo is built milestone-by-milestone — see [docs/milestones.md](docs/milestones.md).
**Current state: Milestone 1 — end-to-end skeleton.** The chat round-trips through
a FastAPI backend to a local Ollama model using a trivial placeholder system
prompt. The real intake flow (Prompt A, spec schema, PRD generation) lands in
later milestones.

## Architecture (Milestone 1)

```
frontend (Next.js + Tailwind)  ──POST /chat──►  backend (FastAPI)
                                                     │
                                                     ▼
                                          llm/provider.generate()   ← the one seam
                                                     │                  for dev/prod swap
                                                     ▼
                                            Ollama (local, /api/chat)
```

The LLM is reached only through `generate(messages, system_prompt)` in
[backend/app/llm/provider.py](backend/app/llm/provider.py). Swapping Ollama for a
cloud provider later is an env-var change (`LLM_PROVIDER`), never a code change.
Any provider API key stays server-side; the frontend never sees it.

## Prerequisites

- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com) running locally with a model pulled:
  ```
  ollama pull llama3.1   # or any model you prefer
  ```

## Run the backend

```bash
cd backend
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env        # then edit .env and set OLLAMA_MODEL=<your model>
uvicorn app.main:app --reload
```

Backend runs on http://localhost:8000. Quick checks:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "history": []}'
```

> `OLLAMA_MODEL` has no default — if it's unset, `/chat` fails fast with a clear
> message telling you to set it.

## Run the frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_BASE_URL defaults to localhost:8000
npm run dev
```

Open http://localhost:3000, type a message, and you should get a reply back from
the model — that's the Milestone 1 round-trip.

## Project layout

```
backend/   FastAPI app + provider router + Ollama client
frontend/  Next.js + Tailwind single-page chat UI
docs/      intake-flow design (Prompt A/B, spec schema) and milestones
```
