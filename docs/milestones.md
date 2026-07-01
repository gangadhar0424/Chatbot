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
- [x] Show the user a summary of the completed spec before generating the PRD,
      with a chance to correct anything
- [x] Wire in Prompt B; render the result as a viewable/downloadable Markdown doc

## Milestone 5 — Production swap
- [x] Provider-router implemented so an env var switches Ollama ↔ cloud API
      with no code change
- [x] API key handled server-side only
- [x] Postgres wired in for persistence (Neon); Redis deferred to deployment

## Milestone 6 — Action layer (phase 2, after the above is solid)
- [x] File/project scaffolding generated from the completed spec
- [ ] Deployment integration
- [ ] Maintenance hooks (docs, monitoring, periodic check-ins)

## Milestone 7 — Evals
- [x] Test framework set up (pytest, isolated from production Neon DB)
- [x] Regression tests for the 4 known bugs: bulk-fabrication of sentinels
      across future sections, priority misgrouping in PRD generation,
      leaked field shapes (mvp_features shape bleeding into other list
      fields), premature section completion
- [x] Scripted end-to-end conversation tests: normal flow, skip-heavy
      flow, terse one-word-answer flow, adversarial/prompt-injection input
- [x] Assertions on final spec state for each scripted conversation
- [x] Stale verify_m4.py test_409_gate replaced by a proper test here

## Milestone 8 — Grounding guardrails
- [x] Runtime check: extracted field values must be grounded in something
      the user actually said (no invented facts)
- [x] Validation beyond shape — catch values that are structurally valid
      but semantically wrong
- [x] Model output confidence scoring before accepting extracted values

## Milestone 9 — Security hardening
- [ ] Prompt-injection resistance tested explicitly
- [ ] Rate limiting on /chat, /generate-prd, and /generate-scaffold
      endpoints
- [ ] Input sanitization review across all user-facing inputs
- [ ] API key rotation plan documented
