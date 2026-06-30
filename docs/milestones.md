# Build milestones

Work through these in order. Check a box only once the feature actually
runs end to end — not just compiles or returns a 200.

## Milestone 1 — Skeleton
- [x] Chat UI: single page, message list + input box
- [x] Backend endpoint that accepts a message + conversation history
- [x] Ollama call wired in (fine to start with a trivial static system prompt
      before swapping in the real Prompt A)
- [x] Round-trip works end to end: type a message, get a model reply back

## Milestone 2 — Real spec tracking
- [x] Implement the full spec JSON schema from docs/intake-chatbot-prompts.md
- [x] Wire in Prompt A exactly as written (combined extraction + next-question
      call, one LLM call per turn)
- [x] Persist spec + conversation history per session (in-memory is fine for now)
- [x] Confirm required fields actually get filled across a real conversation,
      not just on the happy path

## Milestone 3 — Section flow + completion
- [x] _meta.current_section advances correctly through all 9 sections in order
- [x] "unspecified" / ["unspecified"] sentinel handling works when the user
      skips or doesn't know a field
- [x] The structured fields (mvp_features with priority, known_risks with
      impact + mitigation) come back in the correct object shape
- [x] phase flips to "ready_for_prd" only when every field is non-null and
      non-empty — verify this with the backend-side check, not just by
      trusting the model's own "phase" value

## Milestone 4 — PRD generation + confirmation screen
- [ ] Show the user a summary of the completed spec before generating the PRD,
      with a chance to correct anything
- [ ] Wire in Prompt B; render the result as a viewable/downloadable Markdown doc

## Milestone 5 — Production swap
- [ ] Provider-router implemented so an env var switches Ollama ↔ cloud API
      with no code change
- [ ] API key handled server-side only
- [ ] Postgres + Redis wired in for persistence and session cache

## Milestone 6 — Action layer (phase 2, after the above is solid)
- [ ] File/project scaffolding generated from the completed spec
- [ ] Deployment integration
- [ ] Maintenance hooks (docs, monitoring, periodic check-ins)
