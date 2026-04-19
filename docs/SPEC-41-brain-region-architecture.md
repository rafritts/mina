# SPEC-42: Brain Region Architecture — Package Reorganization

## Problem

The codebase has two organizing principles in conflict. `src/sim/` is organized by neuroscience
(neuro/, physio/, psych/, chem/) — brain systems as the primary axis. But `src/bio/`,
`src/runtime/`, and `src/memory/` are organized by technical function (encoder, decoder,
cortex, hippocampus) with no consistent logic about where things live or why.

The result: no clear answer to "what is this file?" or "where does this belong?"

---

## Guiding Principle: Two Packages, Zero Ambiguity

Every file in `src/` belongs to one of two categories:

- **Neuroscience** — models a brain process. Belongs in `src/biology/`.
- **Application** — runs the Discord bot, serves the dashboard, handles infrastructure. Belongs in `src/application/`.

If you can't answer which category a file belongs to in under two seconds, the name is wrong.

---

## Target Structure

```
src/
  biology/                        # Everything that models brain/biology
  │
  │ ┌── amygdala/                 # Stimulus appraisal — reads incoming events,
  │ │     stimulus_encoder.py     # assigns neurochemical significance before
  │ │     __init__.py             # cortical processing
  │ │
  │ ├── subconscious/             # Felt sense synthesis — chemical state →
  │ │     decoder.py              # emotional disposition; idle/DMN processing
  │ │     freetime.py
  │ │     __init__.py
  │ │
  │ ├── cortex/                   # Conscious processing — LLM response,
  │ │     cortex.py               # follow-up, tool orchestration
  │ │     followup.py
  │ │     tools.py
  │ │     __init__.py
  │ │
  │ ├── hippocampus/              # Memory — episodic (RAG) and semantic (KAG)
  │ │     hippocampus.py          # neuroscience layer only; plumbing in application/
  │ │     __init__.py
  │ │
  │ ├── brainstem/                # Autonomic regulation — heartbeat, vital signs,
  │ │     heartbeat.py            # circadian tick, homeostatic maintenance
  │ │     vital_signs.py
  │ │     __init__.py
  │ │
  │ └── sim/                      # Chemical substrate — neurotransmitter dynamics,
  │       neuro/                  # physiology, derived psych states. Unchanged.
  │       physio/
  │       psych/
  │       chem/
  │       bio/
  │       engine.py
  │       ...
  │
  application/                    # Everything that runs the app
  │   gateway/                    # Discord bot, dashboard HTTP server, supervisor
  │   infra/                      # Logging, API client, utilities
  │                               # Includes RAG/ChromaDB client, KAG file I/O —
  │                               # the plumbing the hippocampus sits on top of
  │   skills/                     # Tool integrations (ComfyUI, etc.)
  │
  identity/                       # Mina's persistent self — character files,
  │   MINA.md                     # KAG knowledge, relationship history
  │   CUSTOMIZATION.md
  │   ...
  │
  config/                         # All configuration — JSON and Python
  │   config.json                 ← root config.json
  │   config.py                   ← src/application/infra/config.py
  │
  run/                            # Transient runtime state
      state.json
      decoder_window.json
      bio_snapshots.jsonl
      ...
```

---

## What Moves Where

| Current path | New path | Notes |
|---|---|---|
| `src/bio/encoder.py` | `src/biology/amygdala/stimulus_encoder.py` | Rename file |
| `src/bio/decoder.py` | `src/biology/subconscious/decoder.py` | |
| `src/bio/vital_signs.py` | `src/biology/brainstem/vital_signs.py` | |
| `src/bio/chemicals.py` | delete or inline | Shim — assess at migration time |
| `src/bio/state.py` | delete or inline | Shim — assess at migration time |
| `src/runtime/cortex.py` | `src/biology/cortex/cortex.py` | |
| `src/runtime/followup.py` | `src/biology/cortex/followup.py` | |
| `src/runtime/tools.py` | `src/biology/cortex/tools.py` | |
| `src/runtime/freetime.py` | `src/biology/subconscious/freetime.py` | |
| `src/runtime/heartbeat.py` | `src/biology/brainstem/heartbeat.py` | |
| `src/memory/hippocampus.py` | `src/biology/hippocampus/hippocampus.py` | |
| `src/sim/` | `src/biology/sim/` | Move wholesale, no internal changes |
| `src/gateway/` | `src/application/gateway/` | Move wholesale |
| `src/infra/` | `src/application/infra/` | Move wholesale, except config.py |
| `src/infra/config.py` | `src/config/config.py` | Config lives with config |
| `config.json` (root) | `src/config/config.json` | |
| `identity/` (root) | `src/identity/` | |
| `skills/` (root) | `src/application/skills/` | App integrations, not neuroscience |

---

## What Gets Deleted

`src/bio/`, `src/runtime/`, `src/memory/` cease to exist as packages. Their contents are
rehomed above. The shim files (`chemicals.py`, `state.py`) are deleted if no external call
sites remain after import updates; otherwise left as one-line re-exports.

---

## Import Updates

All internal imports update to match new paths. No logic changes anywhere — this is a
move-and-rename operation only.

Primary call sites to audit:
- `src/gateway/discord_gateway.py` → `src/application/gateway/discord_gateway.py`
- `src/gateway/supervisor.py` → `src/application/gateway/supervisor.py`
- Any skill in `skills/` importing from `bio/`, `runtime/`, or `memory/`
- `main.py` (entry point imports)

---

## Future Homes

New brain region constructs have obvious homes:

| Future spec | Lives in |
|---|---|
| Amygdala emotional tagger (SPEC-41 follow-on) | `src/biology/amygdala/` |
| PFC executive function | `src/biology/cortex/pfc.py` |
| ACC self-monitoring | `src/biology/subconscious/acc.py` |
| DMN rumination | `src/biology/subconscious/dmn.py` |
| Nucleus accumbens | `src/biology/sim/neuro/` |

The question "where does this go?" has a two-step answer: neuroscience or application, then
which region. No file should be ambiguous under this structure.
