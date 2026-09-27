# Mina

A local AI companion whose outputs are **causally driven** by a neurochemical simulation — not a chatbot with mood flavor text layered on a static system prompt.

Chemistry is the body. Brain-region “pillars” (LLM calls with fixed contracts) mediate between the body and the voice. The chat model is the mouth: it receives felt-state and strategy, not raw chemistry numbers.

| Surface | Port | Role |
|---------|------|------|
| Next.js UI | **2050** | Chat, live mind stream, control pane, admin lab |
| FastAPI backend | **5100** | Sim + turn pipeline + admin/state API |

Single-user, local-first. No Discord in v2. No multi-tenant gateway.

---

## Why this exists

Most companions pin personality in a system prompt. That personality does not accumulate experience as state, cannot be in a different chemical condition today than yesterday, and has no body clock between messages.

Mina inverts that:

1. Incoming text is **perceived** (state-blind encoder).
2. Perception drives **deterministic Class-1 chemical deltas** into a live sim.
3. The sim **ticks every 10s** in the background (decay, circadian, opponents, sleep pressure).
4. A **decoder** projects chemistry into pillar-legible numbers (ratio-to-setpoint, not absolute nM).
5. Sequential **pillars** turn projection → felt state → context → response strategy → system prompt.
6. The **mouth** (Mina LLM) answers from that prompt plus a small conversation window.

She has knowledge that a neurosim exists the way a person knows they have a brain — as fact, not as live instrumentation. She cannot read dopamine bars; she feels qualia the pillars invent from chemistry.

Design target: overall **B+ chemical fidelity** (see `docs/chemical_fidelity_tiers.md`). Grade each chemical to the expressivity it unlocks, not to uniform over-modeling. North-star writeup: **`docs/architecture.md`**.

---

## High-level architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  main.py                                                        │
│    • Sim background thread (tick every 10s)                     │
│    • FREETIME asyncio loop (cadence ~2 min check / 30 min min)  │
│    • History snapshot loop (60s)                                │
│    • uvicorn FastAPI gateway :5100                              │
└─────────────────────────────────────────────────────────────────┘
         ▲                              ▲
         │ POST /v1/chat/completions    │ GET/PATCH /api/*
         │ GET  /api/stream (SSE)       │
┌────────┴────────┐            ┌────────┴────────┐
│  Next.js UI     │            │  Admin / control │
│  :2050          │            │  (same UI shell) │
└─────────────────┘            └──────────────────┘
```

### Per-turn pipeline (`src/brain/pipeline.py`)

```
user message
    → Encoder (amygdala)     LLM, state-blind salience axes 0–10
    → Chemistry function     deterministic Class-1 deltas only
    → Decoder                snapshot: normalized / setpoint / gap / rate
    → Insula                 LLM: felt state from decoder + Big 5
    → Memory retrieve        KAG + RAG (sliding + episodic) in parallel
    → Context assembly       LLM summaries of window + RAG
    → Hippocampus pillar     LLM: situational context (framed by felt state)
    → PFC pillar             LLM: strategy + constructs system prompt
    → Mouth (Mina)           LLM: reply JSON (text + optional scene fields)
         optional send_photo tool loop (Comfy / comfy-fe)
    → Persist window, logs, sliding RAG, scene_context.json
```

Pillars are **sequential and cumulative**. Insula reframes what hippocampus treats as notable; hippocampus + felt state feed PFC; mouth never sees raw chemistry.

### Background

| Process | Where | What |
|---------|--------|------|
| Chemistry tick | `src/sim/` | 10s: phasic decay, tonic→setpoint, Class 2/3 cascades, opponents, adenosine, auto-sleep |
| FREETIME | `src/freetime/` | Same pillar chain on a synthetic “you are alone” input; tools (eat, diary, …); output → conversation log for consolidation |
| Consolidation | `src/hippocampus/` | During FREETIME: episodic RAG, KAG diary/knowledge, relationship compaction |
| History | `main.py` | Periodic chemistry snapshots for admin charts |

### LLM transport

All chat/pillar calls go through **`src/application/infra/client.py` → headless Grok Build CLI** (`grok --prompt-file`), not the Nori SDK and not API keys in the child process.

- Auth: interactive `grok login` (shared via symlink of `auth.json` / `config.toml`).
- Sessions: child `GROK_HOME` = `~/.mina/grok` (override `MINA_GROK_HOME`); each oneshot session dir is deleted after parse so interactive `~/.grok/sessions` is not polluted.
- CWD for oneshots: `~/.mina/oneshot` (override `MINA_GROK_CWD`) so project `AGENTS.md` is never loaded into headless runs.
- Optional `XAI_API_KEY` only for FREETIME web/x search via the Responses-style API path — not for the main turn pipeline.

**Do not introduce Nori** for Mina turns. Architecture decision: raw CLI oneshots only.

---

## Repository layout

```
mina/
├── main.py                 # Process entry: sim + FREETIME + gateway
├── config.json             # Local runtime (gitignored template: username, optional big5)
├── identity/
│   └── MINA.md             # Static self / voice / appearance (committed)
│   # CUSTOMIZATION.md      # Optional personal override (gitignored)
├── memory/
│   ├── kag/                # Knowledge files (REFLECTION, KNOWLEDGE/, …) — runtime
│   ├── rag/                # ChromaDB — runtime
│   └── relationships/      # Per-person markdown — runtime
├── run/                    # Runtime state (gitignored): sim_state, windows, scene, logs
├── src/
│   ├── brain/              # Turn pipeline + pillars + scene + chat tools
│   ├── sim/                # Chemical state, tick, chemistry function, decoder, params
│   ├── hippocampus/        # RAG/KAG/relationship store + consolidation
│   ├── freetime/           # Solitary loop + tools
│   ├── gateway/            # FastAPI server
│   ├── application/infra/  # Grok client, stream bus, history, comfy, events
│   └── config/             # Paths, MODEL labels, Big 5 defaults
├── ui/                     # Next.js 16 chat + control + admin
├── scripts/                # install.sh, run.sh, mina CLI
├── docs/
│   ├── architecture.md     # Authoritative v2 design (read this)
│   ├── chemical_fidelity_tiers.md
│   └── neurochemistry/     # Reference notes
└── tests/                  # Sim stability, etc.
```

---

## Chemistry sim (body)

**Module:** `src/sim/`

- **State:** tonic + phasic + setpoint + receptor sensitivity per chemical (`state.py`), persisted to `run/sim_state.json`.
- **Tick:** every 10s (`sim.py` background thread → `tick.py`).
- **External input:** only `Sim.apply_delta` / `apply_chemistry_from_encoder` — conversation, tools, FREETIME, admin all share one interface.
- **Params:** data-only table in `params.py` (weights, half-lives, normalization max, opponent rules). Tune here first when behavior is wrong.

**Classes** (must not be collapsed):

| Class | Examples | Update path |
|-------|----------|-------------|
| 1 Fast NT | DA, 5-HT, NE, epinephrine | Encoder axes → chemistry function deltas |
| 2 Peptides | oxytocin, endorphins, substance P, … | Tick accumulation from sustained Class 1 |
| 3 Hormonal | cortisol (via CRH…), sex hormones, … | Tick / cascade only |
| 4 Scaffold | glutamate, GABA, ACh (as modeled) | Supporting dynamics |

Concentrations are **working nM**. Decoder maps to 0–10 normalized with setpoint, gap, rate. Core chemicals always shown; others only when \|gap\| ≥ 2.

**Big 5** loads from `config.json` → `load_big5()` (defaults in `config.py`). Traits bias chemistry params and insula/PFC prompts. **Traits do not drift**; lasting change is tonic chemistry. Encoder never sees Big 5 or chemistry (state-blind perception).

**Sleep:** high adenosine → auto-sleep until pressure clears (minimum sleep duration enforced). FREETIME skips while sleeping.

---

## Brain pillars (mediators)

| Region | Code | Role |
|--------|------|------|
| Amygdala | `brain/encoder.py` | State-blind 10-axis appraisal (threat, bonding, reward, …) + flags |
| Insula | `brain/insula.py` | Felt state / qualia language |
| Hippocampus pillar | `brain/hippocampus_pillar.py` | Situational summary given felt state + memory |
| PFC | `brain/pfc.py` | Strategy tags + system prompt assembly |
| Mouth | pipeline + `client.chat_create(..., mouth=True)` | User-facing reply + **scene JSON** fields |

Live **scene context** (`brain/scene_context.py`, `run/scene_context.json`): mouth authors clothing/positions/time/timeline/plans; host only stores and re-injects into hippocampus, PFC, and next mouth prompt. Same short-term coherence pattern as Kaiya — host never invents scene facts.

---

## Memory

| Layer | Store | Purpose |
|-------|--------|---------|
| Decoder window | `run/decoder_window.json` | Last ~20 raw messages for assembly |
| Mouth window | in-pipeline | Last ~8 messages to Mina |
| Sliding RAG | Chroma `mina_sliding` | Per-turn chunks + sequence expand |
| Episodic RAG | Chroma `mina_experiences` | Consolidated moments |
| KAG | `memory/kag/` | REFLECTION diary, KNOWLEDGE facts |
| Relationships | `memory/relationships/<user>.md` | Cascading short→medium→long→ground_truth layers |
| Identity | `identity/MINA.md` | Permanent self doc |

Embeddings: Ollama `embeddinggemma:latest` at `http://localhost:11434` (see hippocampus). Without Ollama, RAG paths degrade or fail — chat pillars may still run with thinner memory.

---

## HTTP API (backend :5100)

Primary surface for the UI (Next proxies `/api/*` and chat):

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/chat/completions` | One full pipeline turn (`messages`, optional `image_count`, `image_aspect`, `redo`) |
| GET | `/v1/models` | Stub model list (`mina`) |
| GET | `/health` | Liveness |
| GET/PATCH | `/api/state` | Chemistry snapshot / admin edits |
| POST | `/api/state/advance` | Advance sim time |
| POST | `/api/state/reset` | Chemistry → baseline (keeps chat/memory) |
| POST | `/api/conversation/erase` | Wipe chat window + sliding RAG (keeps chem/KAG) |
| GET | `/api/stream` | SSE mind/stage stream for UI |
| GET | `/api/context` | Last pillar assembly (`?format=md`) |
| GET | `/api/scene` | Live scene snapshot |
| GET | `/api/history` | Chemistry history series |
| GET | `/api/events`, `/api/tokens`, `/api/obs` | Ops / instrumentation |
| POST | `/api/heartbeat` | Manual FREETIME-ish nudge |

Not a multi-client Open WebUI product path by default; local single user.

---

## UI (`ui/`)

Next.js 16 + React 19 + Tailwind. Production port **2050**.

| Route | Content |
|-------|---------|
| `/` | Chat + thought stream + control (presence, chemistry peeks, presets, photo prefs) |
| `/admin/*` | Lab: overview, neuro editors, context, history, events, system |

Chat posts to backend via app routes; mind stream consumes SSE. Build id: `GET /api/build` (also printed by `mina status` / restart). After UI changes: `mina rebuild` or `mina restart` so production `next start` serves a fresh build.

---

## Process management

```bash
./scripts/install.sh     # uv sync, npm install/build, user service, CLI
mina start|stop|restart|status|logs|enable|disable
mina setup               # rewrite service file + ~/.config/mina/tools.env
mina rebuild             # npm build + restart; prints build id
mina update              # git pull + uv sync + npm install + build + restart
mina reset [--yes]       # chemistry baseline via API
mina factory-reset       # wipe run/* chat/sim/RAG (keeps identity)
```

Linux uses a systemd **user** unit. macOS uses LaunchAgent `com.rafritts.mina` (`KeepAlive` → `SuccessfulExit` false; `mina stop` bootouts the agent and stops Ollama). `scripts/run.sh` is the service entrypoint: backend `uv run python main.py` on **5100** + `npm run start` on **2050**. It does not prepend tool directories onto `PATH`. `mina start` / `mina stop` also start and stop Ollama (`:11434`, Homebrew `brew services` when that formula is installed) so RAG embeddings are up before chat. Ollama is not a separate service entry.

`restart`, `rebuild`, `update`, and `status` print `GIVE THIS BUILD ID TO THE USER <id>`. `start` does not.

Dev without the user service:

```bash
uv run python main.py          # :5100
cd ui && npm run dev           # :2050 (dev script already pins host/port)
```

---

## Identity and character

- **`identity/MINA.md`** — voice, appearance, apartment, conversational rules. Loaded into pillar/mouth context.
- **`identity/CUSTOMIZATION.md`** — optional, **gitignored**, appended as personal override.
- **`config.json`** — at least `username` for relationship files; optional `big5` overrides.

Mina is not an assistant persona. She is a character with chemistry, memory, and the right to be unhelpful or distant.

---

## What is not this repo (anymore)

| Item | Status |
|------|--------|
| Discord bot | Removed in v2 |
| Nori SDK / agentic tool harness for turns | Explicitly out of scope |
| v1 6-tier arcade sim and its specs | Removed. `docs/SPEC-60-V1-TOMBSTONE.md` records the cut |
| Root README claims of “Discord DM companion” | Superseded by this document |

For current design decisions, trust **`docs/architecture.md`** + the code under `src/`.

---

## Agent orientation (read order)

If you are an LLM agent ramping on this repo:

1. This README (purpose + map).
2. **`docs/architecture.md`** — principles, pipeline contracts, chemical classes, non-negotiables.
3. **`SETUP.md`** — how to install, auth, verify, common failure modes.
4. Entry points: `main.py` → `src/gateway/server.py` → `src/brain/pipeline.py` → `src/sim/sim.py`.
5. LLM I/O: `src/application/infra/client.py`.
6. UI: `ui/app/page.tsx`, `ui/app/components/ChatApp.tsx`, `ui/app/lib/api.ts`.

When changing behavior:

- Chemistry tuning → `src/sim/params.py` and chemistry/tick — not prompt spaghetti.
- Perception schema → encoder contract + chemistry axis weights together.
- Voice / self → `identity/MINA.md`.
- Turn orchestration / scene / tools → `src/brain/`.
- Never point interactive `GROK_HOME` at Mina-only isolation unless the user asks; oneshots already isolate under `~/.mina/grok`.

---

## License

MIT
