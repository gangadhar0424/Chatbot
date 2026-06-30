# Project: AI project-intake chatbot

A conversational requirements-gathering assistant. It interviews a user about
a software project they want to build, fills in a structured JSON spec
field-by-field (every field required — no skipping, no early exit), and once
every field is filled, generates a professional PRD document.

## Stack
- Frontend: Next.js + Tailwind (or Vite + React)
- Backend: FastAPI (Python)
- Dev LLM: Ollama, local
- Prod LLM: cloud API, swapped in behind one provider-router function — never
  a code change, only an env var
- DB: SQLite (dev) → Postgres (prod)
- Session cache: Redis (prod)

## Key references — read before building anything
- Full intake-flow design (spec schema, Prompt A, Prompt B, orchestrator
  pseudocode): @docs/intake-chatbot-prompts.md
- Current build order and what's done so far: @docs/milestones.md

## Conventions
- Keep the LLM provider behind one interface —
  `generate(messages, system_prompt)` — so dev/prod swap is config, never code.
- The JSON schema in docs/intake-chatbot-prompts.md is the source of truth.
  Don't invent or rename fields without updating that file first.
- Work one milestone at a time from docs/milestones.md. Don't start the next
  milestone until the current one's boxes are checked AND it actually runs —
  not just compiles.
- The API key for the production provider lives server-side only. Never send
  it to, or read it from, frontend code.
