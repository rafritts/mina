# SETUP.md — Mina (for humans and LLM agents)

Operational setup for a working local Mina: chemistry sim + FastAPI + Next UI + headless Grok Build CLI.

If anything here conflicts with `docs/architecture.md` or code under `src/`, **prefer the code** and update this file.

---

## Success criteria

You are done when all of the following hold:

1. `curl -sf http://127.0.0.1:5100/health` → `{"status":"ok"}` (or equivalent).
2. UI answers on `http://localhost:2050/` (or `MINA_UI_PORT`).
3. `grok` is available and logged in (`grok login` once).
4. A chat message in the UI returns a Mina reply (pipeline completes; multi-minute latency is normal).
5. Optional but recommended: Ollama embeddings up so RAG is not empty.

---

## Prerequisites

| Dependency | Version / notes |
|------------|-----------------|
| OS | Linux (systemd user unit) or macOS (LaunchAgent `com.rafritts.mina`) |
| Python | **≥ 3.13** (see `.python-version`) |
| [uv](https://github.com/astral-sh/uv) | On `PATH` or common install paths (`~/.local/bin`, `~/.cargo/bin`) |
| Node.js + npm | **20+** |
| [Grok Build CLI](https://grok.x.ai) | Binary `grok` on `PATH` **or** `~/.grok/bin/grok` |
| Ollama (recommended) | `http://localhost:11434`, model `embeddinggemma:latest` for Chroma embeddings |
| Comfy / comfy-fe (optional) | Photo tool; default `COMFY_FE_URL=http://127.0.0.1:8886` |

Package manager rules for this monorepo:

- Python: **`uv sync` / `uv add`** — do not hand-edit `pyproject.toml` dependency lists unless the project already does so for a specific reason; prefer CLI.
- Node: **`npm install`** inside `ui/`.

---

## 1. Clone and Python deps

```bash
cd /path/to/mina
uv sync
```

Creates `.venv` and installs: FastAPI, uvicorn, chromadb, openai (client types / optional search), pillow, pytest, etc. **No Nori.**

---

## 2. Grok Build auth (required for chat)

Turns use **headless `grok` oneshots**, not `XAI_API_KEY` in the pipeline child.

```bash
# Install Grok Build if needed, then:
grok login
# Verify:
command -v grok || test -x "$HOME/.grok/bin/grok"
```

Isolation (already implemented in `src/application/infra/client.py`):

| Path | Purpose |
|------|---------|
| `~/.grok` | Interactive Grok (auth, your sessions) — do not point Mina here for oneshot storage |
| `~/.mina/grok` | Child `GROK_HOME`; `auth.json` / `config.toml` symlinked from `~/.grok`; oneshot sessions deleted after each call |
| `~/.mina/oneshot` | Child cwd so repo `AGENTS.md` is not injected |

Overrides (optional env):

| Variable | Default | Meaning |
|----------|---------|---------|
| `GROK_BIN` | auto-detect | Path to `grok` binary |
| `MINA_GROK_HOME` | `~/.mina/grok` | Isolated Grok home for oneshots only |
| `MINA_GROK_CWD` | `~/.mina/oneshot` | Oneshot working directory |
| `MINA_GROK_TIMEOUT_MS` | `180000` | Per-call timeout |

Do **not** set process-wide `GROK_HOME` to Mina’s isolation path for interactive use unless the operator explicitly wants that.

---

## 3. Optional `.env`

`.env` is gitignored. Create at repo root if needed:

```bash
# Optional — FREETIME web/x search only (not main chat pipeline)
# XAI_API_KEY=...

# Ports (also set by the user service: UI 2050, backend 5100)
# MINA_BACKEND_PORT=5100
# MINA_UI_PORT=2050
# MINA_BACKEND_HOST=127.0.0.1

# Photo generation frontend
# COMFY_FE_URL=http://127.0.0.1:8886

# Labels only (CLI uses logged-in default model)
# MODEL=grok-4.3
# CONTEXT_MODEL=grok-4.3
```

`main.py` loads `.env` before importing config-backed modules.

---

## 4. Local config

`config.json` is gitignored. Minimal example:

```json
{
  "username": "ryan"
}
```

`reasoning_effort` is sent on every headless Grok call (`low`, `medium`, `high`, or `xhigh`). Omitted or `none` means `low`.

Optional Big 5 overrides (0–100); omitted keys use defaults in `src/config/config.py`:

```json
{
  "username": "ryan",
  "reasoning_effort": "low",
  "big5": {
    "openness": 72,
    "conscientiousness": 55,
    "extraversion": 48,
    "agreeableness": 68,
    "neuroticism": 65
  }
}
```

`username` keys relationship files under `memory/relationships/`.

Optional personal identity: `identity/CUSTOMIZATION.md` (gitignored) is appended to identity context when present.

---

## 5. UI deps

```bash
cd ui
npm install
npm run build    # production
# or: npm run dev  # development on :2050
```

---

## 6. Install service + CLI

From repo root:

```bash
./scripts/install.sh
```

This:

1. `uv sync` + `ui` npm install/build
2. Writes `~/.config/mina/dir` (repo path) and `~/.config/mina/tools.env` (absolute `uv` / `npm`, service `PATH`, ports)
3. Symlinks `~/.local/bin/mina` → `scripts/mina`
4. Installs a **user** service that runs `scripts/run.sh` (backend **5100** + UI **2050**):
   - Linux: `~/.config/systemd/user/mina.service` (`systemctl --user`)
   - macOS: `~/Library/LaunchAgents/com.rafritts.mina.plist` (`launchctl`). `KeepAlive` is `SuccessfulExit=false` (not blanket true). Logs: `~/Library/Logs/mina.log`. `mina stop` is `launchctl bootout`.
5. Enables login autostart and starts, unless you only rewrite the service file:

```bash
./scripts/install.sh --setup-only   # service file + tools.env only
mina setup                          # same
```

The service does not read the shell rc. `PATH` is whatever install wrote. Re-run `mina setup` when Node, npm, or uv moves, then restart. `~/.local/bin` must be on the interactive `PATH` so the `mina` command resolves.

### CLI cheatsheet

```bash
mina help
mina start | stop | restart | status
mina enable | disable         # login autostart only; does not start or stop
mina logs [-f] [-n 200]       # journalctl on Linux; ~/Library/Logs/mina.log on macOS
mina rebuild                  # npm build + restart; prints build id
mina update                   # git pull + uv sync + npm install + build + restart
mina reset [--yes]            # chemistry baseline via API (keeps memory)
mina factory-reset [--yes]    # wipe run chat/sim/RAG state; restart
```

`start` waits until ready and does **not** print the build id. After `restart` / `rebuild` / `update` / `status`, the CLI prints two lines. Copy the first unchanged:

```text
GIVE THIS BUILD ID TO THE USER <id>
Build: {"id":"<id>","git":"<short>","builtAt":"<iso>"}
```

---

## 7. Run without the user service (dev)

Terminal A:

```bash
cd /path/to/mina
uv run python main.py
# Backend: http://0.0.0.0:5100
```

Terminal B:

```bash
cd /path/to/mina/ui
npm run dev
# UI: http://0.0.0.0:2050
```

Production-style without the user service:

```bash
./scripts/run.sh
# frees ports if needed; starts backend then npm run start
```

---

## 8. Ollama embeddings (RAG)

Hippocampus expects:

- Base URL: `http://localhost:11434`
- Model: `embeddinggemma:latest`

```bash
# Example — adjust to your Ollama install
ollama pull embeddinggemma:latest
curl -sf http://localhost:11434/api/tags
```

Without embeddings, consolidation/retrieval may error or return empty; the rest of the pipeline can still answer with thinner context.

---

## 9. Verify

```bash
# Backend
curl -sf http://127.0.0.1:5100/health

# State snapshot
curl -sf http://127.0.0.1:5100/api/state | head -c 400; echo

# UI
curl -sf -o /dev/null -w "%{http_code}\n" http://127.0.0.1:2050/

# Build id (production UI)
curl -sf http://127.0.0.1:2050/api/build; echo

# One chat turn (slow — full multi-pillar + mouth)
curl -s http://127.0.0.1:5100/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"ping"}],"image_count":0}' \
  | head -c 800; echo
```

Expect chat latency on the order of **tens of seconds to a few minutes** (encoder + 3 pillars + context assembly + mouth, each a Grok oneshot).

Check oneshot isolation after a turn:

```bash
# Should stay small / empty of long-lived session dirs under Mina home
ls -la ~/.mina/grok/sessions 2>/dev/null || true
# Interactive pile should not grow from Mina oneshots
# (old path was ~/.grok/sessions/%2Fhome%2F...%2F.mina%2Foneshot — obsolete)
```

---

## 10. Runtime data (do not commit)

| Path | Contents |
|------|----------|
| `run/sim_state.json` | Live chemistry |
| `run/decoder_window.json` | Rolling message window |
| `run/scene_context.json` | Mouth-authored scene |
| `run/conversation-YYYY-MM-DD.jsonl` | Daily log |
| `run/last_context.json` / `.md` | Last pillar assembly dump |
| `run/history.jsonl`, `obs.jsonl`, … | Charts / observer |
| `memory/rag/` | Chroma DB |
| `memory/kag/` | Diary / knowledge |
| `memory/relationships/` | Per-user relationship MD |
| `.env`, `config.json`, `identity/CUSTOMIZATION.md` | Secrets / personal |

`mina factory-reset` clears most of `run/` + RAG (not `identity/MINA.md`).  
`mina reset` only resets chemistry via the live API.

---

## 11. Common failures

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| 503 on chat | Sim not set / backend not `main.py` | Start via `main.py` or `mina start`, not bare uvicorn without `set_sim` |
| Chat errors / empty | `grok` missing or not logged in | Install CLI, `grok login` |
| Timeout mid-turn | Slow model / hung oneshot | Raise `MINA_GROK_TIMEOUT_MS`; check `mina logs -f` |
| Port in use | Stale process | `mina stop`; `scripts/run.sh` frees ports; or `fuser -k 5100/tcp 2050/tcp` |
| UI stale after code change | Production serves last `npm run build` | `mina rebuild` or `mina restart` |
| Empty memory / embed errors | Ollama down / wrong model | Start Ollama, pull `embeddinggemma:latest` |
| Photos never send | comfy-fe down or `image_count: 0` | Start comfy-fe; set photo count in UI |
| Chemistry death spiral | Old state / bad params | `mina reset`; inspect `src/sim/params.py` EVENT_GAIN / sleep thresholds |
| Sessions filling `~/.grok` | Pre-isolation build or wrong GROK_HOME | Use current client.py; do not set child env to interactive home |

---

## 12. Tests

```bash
cd /path/to/mina
uv run pytest
# Integration / live LLM tests may be marked; avoid unless requested
```

Primary unit coverage today is sim stability-oriented; full turn pipeline tests need live Grok.

---

## 13. Agent checklist (first session on a machine)

```text
[ ] Python 3.13+, uv, Node 20+, grok CLI present
[ ] uv sync
[ ] grok login
[ ] config.json with username
[ ] Optional: .env, CUSTOMIZATION.md, Ollama, comfy-fe
[ ] ./scripts/install.sh  OR  main.py + npm run dev
[ ] health + UI + one chat turn
[ ] After UI edits: mina rebuild and report build id to user
[ ] Do not add Nori; do not route turns through API keys in child env
[ ] Do not commit run/, memory/rag, .env, CUSTOMIZATION.md
```

For product purpose and module map, see **`README.md`**.  
For design non-negotiables (state-blind encoder, Class 1–3 routing, pillar order, FREETIME), see **`docs/architecture.md`**.
