# SPEC-09: Mina Dashboard

A web dashboard for monitoring and controlling Mina's biological state in real time.

## Goals

1. **Visibility** — see all biomarkers, derived values, current monologue, and relationship state at a glance
2. **Control** — adjust any neurotransmitter directly via slider (dev/testing; no LLM needed)
3. **Injection** — send a one-shot text fragment that gets prepended to Mode 1's subconscious context on the next turn
4. **Parity with Raika** — same tech stack (SvelteKit 5, Tailwind 4, DaisyUI 5, FastAPI), same bearer-token auth pattern

---

## Architecture

```
dashboard/          ← SvelteKit app
  src/
    lib/api.ts      ← apiFetch helper, SSE reader
    routes/
      +layout.svelte
      +page.svelte          ← redirect → /state
      state/+page.svelte    ← biomarker sliders + derived values
      monologue/+page.svelte
      inject/+page.svelte   ← subconscious injection input
      relationship/+page.svelte
  package.json

dashboard_server.py ← FastAPI server (new file in project root)
```

The FastAPI server runs as a sidecar alongside `supervisor.py`. It reads/writes the same flat files (`state.json`, `run/monologue.md`, `memory/kag/RELATIONSHIP.md`) that the bot uses. No shared in-process state—file I/O is the interface.

---

## Backend — `dashboard_server.py`

### Auth

Bearer token from env var `DASHBOARD_TOKEN`. All routes except `GET /healthz` require it.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/healthz` | liveness check |
| `GET` | `/api/state` | full BiologicalState + derived second/third-order values |
| `PATCH` | `/api/state` | overwrite one or more first-order fields (validated 0–100) |
| `GET` | `/api/monologue` | current `run/monologue.md` content |
| `GET` | `/api/relationship` | `memory/kag/RELATIONSHIP.md` content |
| `POST` | `/api/inject` | write text to `run/subconscious_inject.md`; consumed once on next turn |

#### `GET /api/state` response shape

```json
{
  "first_order": {
    "sleep_pressure": 31.2,
    "glucose": 68.4,
    "hydration": 71.0,
    "cortisol": 27.8,
    "dopamine": 60.1,
    "serotonin": 55.3,
    "norepinephrine": 21.6,
    "oxytocin": 18.9,
    "endorphins": 9.2,
    "acetylcholine": 57.8,
    "melatonin": 12.0,
    "sleeping": false
  },
  "second_order": {
    "energy": 63.1,
    "cognitive_clarity": 58.4,
    "hedonic_tone": 52.7,
    "social_warmth": 43.2,
    "arousal": 34.1,
    "mood_valence": 57.9
  },
  "third_order": {
    "anxiety": 18.3,
    "depression": 22.1,
    "boredom": 31.5,
    "loneliness": 29.8,
    "flow": 44.6
  }
}
```

#### `PATCH /api/state` request shape

```json
{ "dopamine": 70.0, "oxytocin": 35.0 }
```

- Only fields in `_DELTA_FIELDS` (state.py) are accepted; unknown keys → 422
- Values clamped to 0–100
- Loads state, sets fields directly (not as deltas), saves — does NOT call `advance()` (no time decay side-effect on a manual edit)

#### `POST /api/inject` request shape

```json
{ "text": "She's been thinking about her last dream. Keep that color in the air." }
```

Writes content to `run/subconscious_inject.md` (overwrites any pending injection — only one at a time).

---

## Injection Consumption — changes to `main.py` / `subconscious.py`

`run/subconscious_inject.md` is a one-shot file:

1. **Where it's read:** At the top of `run_mode1()` in `subconscious.py`, before building the Mode 1 prompt
2. **How it's consumed:**
   - If file exists, read its content, then **delete the file**
   - Append to the Mode 1 user prompt as: `\n\n[SUBCONSCIOUS INJECTION]\n{text}`
3. **Separation from ADMIN_INSTRUCTIONS:** Admin instructions go to the *main turn* (Mina's visible response context). Subconscious injection goes to *Mode 1 synthesis* (shapes her inner state and monologue, invisible to the user).

---

## Frontend — SvelteKit

### `/state` — Biomarker Control Panel

Layout: two columns

**Left — First-order sliders**

Three groups:

*Homeostatic*
- sleep_pressure, glucose, hydration

*Neuromodulators*
- cortisol, dopamine, serotonin, norepinephrine, oxytocin, endorphins, acetylcholine, melatonin

Each slider:
- Range 0–100, step 0.5
- Label with current numeric value + range label (from `bio_report.py` label bands)
- Color-coded: red if critical/depleted, amber if elevated, green if normal, blue if optimal
- On input: debounce 400ms → PATCH /api/state
- `sleeping` shown as a badge (no slider)

**Right — Derived values**

Second-order: energy, cognitive_clarity, hedonic_tone, social_warmth, arousal, mood_valence — display as progress bars, read-only

Third-order: anxiety, depression, boredom, loneliness, flow — displayed as smaller badges with color intensity

Auto-refresh: poll `/api/state` every 5 seconds; slider thumb only updates if not currently being dragged (avoid fighting the user)

### `/monologue` — Inner Monologue

- Displays full text of `run/monologue.md`
- Shows timestamp of last modification
- Auto-refresh every 10 seconds

### `/inject` — Subconscious Injection

- Textarea (full-width)
- "Send Injection" button → POST /api/inject
- Shows confirmation: "Queued — will be consumed on next turn"
- Shows whether an injection is currently pending (file exists) — polling `/api/inject/pending` (simple GET that returns `{ pending: bool, text: string | null }`)
- "Clear" button → DELETE /api/inject

Add `GET /api/inject/pending` and `DELETE /api/inject` endpoints to backend.

### `/relationship` — KAG Relationship

- Raw markdown rendered as HTML
- Auto-refresh every 30 seconds

### Navigation

Top nav bar (same pattern as Raika): State | Monologue | Inject | Relationship

---

## Range Labels

Copy the label bands from `bio_report.py` into a frontend lookup table (`src/lib/labels.ts`) so sliders can show the current named state without an API round-trip.

---

## Running

```
# Backend (add to supervisor or run separately)
uv run dashboard_server.py --port 7843

# Frontend (dev)
cd dashboard && npm run dev

# Frontend (prod)
cd dashboard && npm run build && npm run preview
```

Port 7843 chosen to avoid conflict with Raika (7842).

---

## Open Questions / Not in Scope

- **Conversation history viewer** — not in this spec; conversation.json can be large and needs pagination
- **Checkpoint management** — rollback/restore UI is useful but scope-expanding
- **Live push (SSE/WebSocket)** — polling is sufficient for v1; state changes are file-based and infrequent
- **Multi-user auth** — single bearer token is fine for local dev
- **Tolerance display** — tolerance dict (caffeine/alcohol) is niche; omit for now
