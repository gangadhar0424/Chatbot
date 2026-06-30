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

## 2026-06-30 — .gitignore files in templates

**Decision: store as `gitignore` (no dot), rename to `.gitignore` on copy**

If `.gitignore` files were stored verbatim inside the chatbot repo, their
ignore rules would apply within those template subdirectories (which is
harmless but confusing). The generator renames `gitignore` → `.gitignore`
during the copy step so the output project gets the correct filename.
Same for `env.example` → `.env.example` to avoid accidentally leaking a
real `.env` from a template directory.
