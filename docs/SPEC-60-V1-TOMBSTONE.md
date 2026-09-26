# SPEC-60 — V1 Tombstone

**Status:** Complete  
**Date:** 2026-05-02  
**Update:** 2026-09-26 — `archive/v1/` and `docs/archive/v1/` were deleted from the repo. This file is the remaining record.

---

## Overview

The v1 biological simulation — 6-tier neurotransmitter engine, 85 modules, 60 specs, Next.js dashboard — was archived, then removed from the tree. What remained at the time of the cut was the minimal Discord + xAI shell needed to build on top of.

The rule: **does this code have value without the simulation?** If yes, keep it. If it exists only to serve the sim, archive it.

---

## Keep

Untouched. No changes needed.

| File | What it is |
|------|------------|
| `src/application/gateway/supervisor.py` | Async entry point and bot lifecycle |
| `src/application/gateway/discord_ui.py` | Avatar confirmation view and REST avatar change |
| `src/application/infra/log.py` | Logging setup |
| `src/application/infra/discord_send.py` | Message sending helpers |
| `src/application/infra/image_utils.py` | Image resize/encode utility |
| `src/application/infra/token_stats.py` | API token usage tracker |
| `ui/` | Entire Next.js dashboard |
| `scripts/install.sh` | Setup script |
| `scripts/uninstall.sh` | Teardown script |
| `scripts/mina` | CLI wrapper |

Project root: `pyproject.toml` (trimmed), `uv.lock`, `.env`, `.python-version`, `.gitignore`.

---

## Strip

Kept but sim-specific content removed.

| File | What was removed |
|------|-----------------|
| `src/config/config.py` | All sim path constants (`STATE_FILE`, `DECODER_WINDOW_FILE`, etc.) and `load_config()`; per-role model overrides (`ENCODER_MODEL`, etc.); kept `REPO_ROOT`, `RUN_DIR`, `MODEL`, `BASE_URL`, `API_KEY`, `get_conversation_file()` |
| `src/application/gateway/discord_gateway.py` | All sim imports (`brain`, `engine`, `freetime`, `heartbeat`); sleep/wake logic; freetime/followup/presence background loops; `_dynamic_freetime_interval`; `_seed_channel`; stream bus registration; allowlist config reads; `_run_turn` stubbed with `NotImplementedError` |
| `src/application/gateway/discord_commands.py` | All sim commands (`state`, `bioreport`, `compress`, `sleep`, `wake`, `heartbeat`, `freetime`, `pause`, `resume`, `context`, `fix-false-positive`, `actions`, `reset`, `factory-reset`); `_wipe_user_data`; `_load_config`; kept `cancel`, `cancel-all`, `stop`, `restart`, `clean`, `set-avatar`, `history`, `new` |
| `src/application/gateway/dashboard_server.py` | All sim routes (`/api/state`, `/api/state/advance`, `/api/heartbeat`, `/api/substance/*`, `/api/history`); all state helper code; kept `/healthz`, `/api/billing`, `/api/tokens`, `/api/events`, `/api/stream` |
| `src/application/infra/client.py` | Per-role model imports (`ENCODER_MODEL`, `DECODER_MODEL`, `CONTEXT_MODEL`) |
| `src/application/infra/events.py` | Sim-specific event shapes (`emit_tool` with delta fields); simplified to generic JSONL append/rotate/read |

---

## Removed from the repo

These trees lived under `archive/v1/` and `docs/archive/v1/` until 2026-09-26. They are gone.

**Code** (mirrored original paths):
- `src/brain/` — cortex, amygdala, hippocampus, subconscious, brainstem
- `src/engine/` — state tick engine, all biological tier modules
- `src/application/tools/` — bio_report, sim_baseline
- `src/application/infra/stream_bus.py` — simulation IPC / dashboard SSE
- `identity/` — config, prompts, character files
- `memory/` — KAG knowledge files
- `run/` — runtime state files
- `logs/` — log files
- `tests/` — entire test suite
- `scripts/chat_sim.py`, `sim_decay_test.py`, `validate.py`, `factory_reset.py`, `convos/`
- `main.py`, `docker-compose.yml`, `toolbox/`

**Specs** that were under `docs/archive/v1/`: SPEC-00 through SPEC-59, SPEC-MANIFEST.md, and the legacy spec-* files.

---

## Final `src/` Structure

```
src/
  config/
    config.py
  application/
    gateway/
      supervisor.py
      discord_gateway.py
      discord_commands.py
      discord_ui.py
      dashboard_server.py
    infra/
      client.py
      log.py
      discord_send.py
      image_utils.py
      token_stats.py
      events.py
```
