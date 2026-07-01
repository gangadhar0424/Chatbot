# Operations runbook

Operational procedures for the project-intake chatbot backend.

---

## API key rotation

The production LLM provider key (`OPENAI_API_KEY`, or the equivalent for
whichever cloud provider is active) is the single highest-value secret in
this system. It is stored server-side only and never sent to the frontend
or committed to the repository.

### When to rotate

| Trigger | Action |
|---|---|
| **Suspected compromise** | Rotate immediately — see *Leak response* below |
| **Team member departure** | Rotate within 24 hours of offboarding confirmation |
| **Scheduled rotation** | Every 90 days, regardless of any incident |
| **Provider-side alert** | Rotate as soon as the provider notifies of unusual usage |

### Which files need updating

1. **`backend/.env`** — the local development file. Update `OPENAI_API_KEY`
   (or the relevant variable name). This file is `.gitignore`d and must never
   be committed.
2. **Deployed environment** — wherever the app runs in production (e.g. a
   cloud provider's secret manager, a platform-as-a-service environment
   variable panel, or a deployment configuration file). The specific location
   depends on the deployment target chosen during intake. The variable name
   must match what `backend/app/llm/provider.py` reads.
3. **Any CI/CD pipeline secrets** — if the key is stored in GitHub Actions
   secrets (or equivalent), update it there too so automated deployments
   get the new key.

After updating, restart the backend service so it picks up the new value.
Verify with a single test request before marking the rotation complete.

### Leak response (key suspected compromised)

**Do these three steps in order, as fast as possible:**

1. **Revoke the key immediately** — go to the provider's API key management
   console and invalidate the compromised key. Do not wait to investigate
   first; stopping the bleeding takes priority. A revoked key causes errors
   in the running app, but that is a recoverable outage; continued unauthorised
   use is not.

2. **Check usage logs** — once the key is revoked, review the provider's
   usage dashboard for the period of suspected exposure. Note: (a) total
   spend above the expected baseline, (b) any unusual models or endpoints
   called, (c) request volume spikes by time-of-day. Export the log and
   retain it in case a post-incident review is needed.

3. **Rotate and redeploy** — generate a new key, update all locations listed
   under *Which files need updating* above, and redeploy the backend. Confirm
   the service is healthy with a test request, then notify any team members
   who need to update their local `.env`.

After the immediate response, conduct a brief post-incident review to
determine how the key was exposed and whether any tighter controls
(secret scanning, shorter rotation interval, narrowed key permissions) are
warranted.

---

## Neon database (`DATABASE_URL`)

The Neon connection string includes credentials and should be treated with
the same care as the API key. Rotate it via the Neon console if a team
member departs or if the string appears in logs or source control. Update
`backend/.env` and the deployed environment variable, then restart the
backend.

---

## Rate-limit tuning

Production rate limits are set via environment variables read at startup
(see `backend/app/main.py`):

| Variable | Default | Endpoint |
|---|---|---|
| `RATE_LIMIT_CHAT` | `30/minute` | `POST /chat` |
| `RATE_LIMIT_PRD` | `5/minute` | `POST /generate-prd` |
| `RATE_LIMIT_SCAFFOLD` | `5/minute` | `POST /generate-scaffold` |

Adjust these in the deployment environment without changing code. A normal
intake interview is 20–30 turns, so 30/minute per IP gives comfortable
headroom. If traffic patterns change (e.g., an embedded iframe with many
concurrent users), increase the limit or switch to a shared Redis storage
backend (replace `MemoryStorage` with `RedisStorage` in `main.py`'s
`Limiter` constructor — the slowapi API is unchanged, only the storage URI).
