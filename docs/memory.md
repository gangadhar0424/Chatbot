# Decision log — Milestone 6 (file generation)

Running log of non-obvious choices made during implementation.
Append entries as you go; do not rewrite this file.

---

## 2026-06-30 — Template library

**Decision: three templates (nextjs-fastapi, nextjs-node, generic)**

The intake spec's `tech_stack_preference` field is a free-text string, so
the possible values are open-ended. However the chatbot's own recommended
stack is Next.js + FastAPI, and those two plus a pure-JS variant (Next.js +
Express) cover the large majority of responses likely to come out of the
intake flow. Everything else falls to `generic` — a flat `src/` folder with
a minimal hello-world. This is intentionally honest: a wrong skeleton is
worse than a minimal one.

Why not Django, Vue, etc.? Those would require additional templates and
matching rules for a long tail of uncommon inputs. Deferred — can be added
one template at a time if they come up in practice.

---

## 2026-06-30 — Template matching approach

**Decision: keyword scanning, not fuzzy scoring or ML**

`tech_stack_preference` is typically 3–10 words ("React + FastAPI +
PostgreSQL"). Keyword scanning is transparent (easy to read and debug),
correct for the expected inputs, and adds zero dependencies. Embedding-based
similarity would be overkill for a short controlled-vocabulary field.

**Match tiers (first match wins):**
1. `next`/`nextjs` + `fastapi`/`python` → `nextjs-fastapi` (exact)
2. `next`/`nextjs` + `node`/`express` → `nextjs-node` (exact)
3. `react` + `fastapi`/`python` → `nextjs-fastapi` (approximate)
4. `react` + `node`/`express` → `nextjs-node` (approximate)
5. anything else → `generic` (fallback)

**Approximate matches surface a note.** When the "next/nextjs" keyword is
absent but we still matched (rules 3–4), the generated README includes an
explicit note: "Scaffolded as Next.js (closest match to your React + FastAPI
preference…)". This keeps the honesty principle consistent with how the
`generic` fallback already works — no silent mismatch.

---

## 2026-06-30 — P0 stub strategy

**Decision: two stubs per P0 feature for web templates (frontend page + backend route)**

For `nextjs-fastapi` and `nextjs-node`, each P0 feature gets:
- `frontend/app/{slug}/page.tsx` — a Next.js page stub
- `backend/app/routes/{slug}.py` (or `.js`) — a route stub

Reason: it is not possible to reliably determine from a feature name alone
whether it primarily lives on the frontend, backend, or both. Creating one
stub per layer — even if one turns out not to be needed — gives the user a
concrete starting point in both places without guessing. Deleting an
unneeded stub file is a five-second operation; writing the first stub from
scratch takes much longer.

Each stub contains only a single TODO comment. Deliberately minimal so it
is unmistakably a placeholder rather than half-finished code.

---

## 2026-06-30 — Dynamic file generation

**Decision: Python f-strings, not Jinja2**

Only two file types are generated dynamically: README.md and P0 stub files.
The templates are simple enough (one heading block, one table, one comment)
that a templating engine adds a dependency for minimal gain. f-strings are
readable, already available, and do not require an install step.

If the scaffolding ever needs conditionals, loops, or inheritance in
generated files, migrate to Jinja2 at that point.

---

## 2026-06-30 — Output directory

**Default: `backend/generated/{slug}-{timestamp}/`**

Configurable via `SCAFFOLD_OUTPUT_DIR` env var. The timestamp suffix
prevents collisions if the user generates a second scaffold for the same
project. The user is expected to move the generated folder to wherever they
want to start work.

Nothing is run in the generated folder (no npm install, no pip install,
no git init) — explicitly excluded per the milestone spec.

---

## 2026-07-01 — Why Milestones 7–9 exist

**Context: all reliability bugs found so far were caught through manual
19-turn test runs.**

Every known bug in the intake flow (bulk sentinel fabrication, priority
misgrouping in the PRD, mvp_features object shape bleeding into plain
list fields, premature section completion) was discovered by running a
full conversation by hand and eyeballing the resulting spec JSON. That
process is slow, human-error-prone, and doesn't scale — a one-line
change to flow.py or a prompt tweak can silently reintroduce any of them.

Milestones 7–9 formalise those manual checks into three layers:
- **M7 Evals**: pytest suite that replays scripted conversations with a
  mocked LLM and asserts on final spec state. Specific regression tests
  for each known bug. The old standalone verify_m4.py becomes a proper
  test here.
- **M8 Grounding guardrails**: runtime checks that extracted values must
  be traceable to something the user actually said, plus validation
  beyond bare shape-checking.
- **M9 Security hardening**: explicit prompt-injection tests, rate
  limiting, and input sanitisation across all user-facing endpoints.

The driving principle: a bug that was found once manually should be
impossible to reintroduce silently.

---

## 2026-07-01 — Project complete (Milestones 1–9)

**Status: all nine milestones done; 57/57 tests passing.**

1. Skeleton — chat UI + backend + Ollama round-trip
2. Real spec tracking — full schema, Prompt A wired in, session persistence
3. Section flow + completion — ordered sections, sentinel handling,
   structured field shapes, backend-verified `ready_for_prd`
4. PRD generation + confirmation screen — spec review before generation,
   Prompt B wired in, downloadable Markdown output
5. Production swap — provider-router (Ollama ↔ cloud), server-side API
   key, Neon Postgres persistence
6. Action layer (partial) — project scaffolding from completed spec;
   deployment integration and maintenance hooks deferred (see below)
7. Evals — pytest suite, regression tests for all four known bugs,
   scripted end-to-end conversation tests
8. Grounding guardrails — extraction grounded in user input, structural +
   semantic validation, confidence scoring
9. Security hardening — prompt-injection resistance, rate limiting on
   /chat, /generate-prd, /generate-scaffold, input sanitisation review,
   API key rotation plan documented

**Known open items (not yet done):**
- OpenAI runtime test — the cloud provider path in the router is wired
  but not exercised against a real OpenAI call in CI/eval.
- Model adherence on cloud model — Prompt A/B behavior (JSON contract,
  section-order discipline) has only been manually spot-checked against
  a cloud model, not covered by the eval suite the way Ollama is.
- Redis / deployment — Milestone 6's deployment integration and
  maintenance hooks are unstarted; session cache is still in-memory/DB,
  no Redis, no deployment target wired up.

---

## 2026-07-02 — M8: old-vs-new stack comparison + two bug fixes

**Context: before removing the old stack (frontend/, backend/app/main.py),
ran the same scripted conversation against both backend/app/main.py (:8000,
Postgres) and backend/web_app.py (:8001, SQLite) and diffed spec_json, PRD
output, and scaffold output.**

**Result: M8 passed — no regression from the rewrite.** Final spec_json
matched field-for-field on identical input; scaffold output was identical
(template, file list); the one PRD-generation bug found reproduced
identically on both stacks, confirming it predates the rewrite.

**Bug found #1 — PRD truncation.** Prompt B (`generate-prd`) intermittently
cut off mid-document on the local 3B model (qwen2.5:3b), as short as
~1,100 chars on a spec that should produce ~5,000. Reproduced on both
stacks. An Ollama probe returned `done_reason: "stop"` (the model choosing
to end, not hitting a length cap) on an unrelated prompt, so the exact
mechanism isn't fully understood — but empirically, adding an explicit
`num_predict=4096` cap on the Prompt B call (`llm_core.llm_call_async`,
wired in via `prd_routes.py`'s `_PRD_NUM_PREDICT`) eliminated truncation
across all post-fix trials (0/6 truncated vs. 4/5 before). Old stack
(`app/main.py`) was left unpatched since it's slated for removal.

**Bug found #2 — risk-tier / priority-tier mislabeling.** `_prepare_spec_for_prd`
pre-groups `known_risks` by impact (High/Medium/Low) and `mvp_features` by
priority (P0/P1/P2) into JSON keys and instructs the model to "transcribe,
don't re-sort." The model ignores that instruction unpredictably — shifting
a risk up a tier, collapsing risks into one bucket, or inventing a risk to
fill an empty one. Same story for the M8 test's untested but same-mechanism
mvp_features grouping.

**Fix: stopped asking the model to transcribe these groupings at all.**
`_prepare_spec_for_prd` (prd_routes.py only — old stack is being removed, no
need to backport) no longer sends `mvp_features`/`known_risks` data to the
model; instead it instructs Prompt B to emit literal marker tokens
(`[[RENDER:MVP_FEATURES]]`, `[[RENDER:KNOWN_RISKS]]`) in their place. After
the call, `_insert_rendered_blocks` replaces those markers with markdown
rendered directly from the spec's already-structured data (pure formatting,
no LLM involved) — with a heading-based fallback insertion for when the
model mangles or drops the marker (observed: it sometimes emits
`[RENDER:...]` with single brackets). Verified 3/3 correct labeling across
fresh generations post-fix, vs. wrong every time before.

**Known minor issue, not a blocker:** the model doesn't fully honor "don't
write this part yourself" — it sometimes also writes its own redundant
version of the Scope/Risks content alongside the correctly-inserted block,
so the PRD can show mild duplication (e.g., "Should-have (P1): None
specified" appearing twice) in the affected sections. The correct,
accurately-labeled data is always present; explicitly decided not to chase
this with fragile text-matching/dedup logic — logging as a known cosmetic
issue for later rather than fixing now.

---

## 2026-06-30 — .gitignore files in templates

**Decision: store as `gitignore` (no dot), rename to `.gitignore` on copy**

If `.gitignore` files were stored verbatim inside the chatbot repo, their
ignore rules would apply within those template subdirectories (which is
harmless but confusing). The generator renames `gitignore` → `.gitignore`
during the copy step so the output project gets the correct filename.
Same for `env.example` → `.env.example` to avoid accidentally leaking a
real `.env` from a template directory.
