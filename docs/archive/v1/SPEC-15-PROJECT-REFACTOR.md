# SPEC-15: Project Refactor — Structure, Naming, and SRP

## Overview

The core simulation loop has grown organically into ~6,600 lines across 18 flat files in the project root. This spec catalogs the tech debt and proposes a target structure. The goal is clarity and maintainability — not purity. Pragmatic over dogmatic.

**In scope:** The 16 `.py` files in the project root (Mina's simulation core).  
**Out of scope:** `skills/`, `dashboard_server.py`, `supervisor.py`, and all frontend/Discord presentation concerns.

---

## Mental Model: The Signal Flow

Before the file map, understand the signal flow. Everything else follows from this.

```
EXTERNAL WORLD
      │
      ▼  (message, event, action)
 ┌──────────┐
 │ encoder  │  External events → neurochemical deltas → applied to simulation
 └──────────┘
      │
      ▼  (BiologicalState updated)
 ┌──────────┐
 │  state   │  Ground truth. Chemical values, sleep, tolerance, substances.
 └──────────┘
      │
      ▼  (state queried)
 ┌──────────┐
 │ decoder  │  Neurochemical state → English prose → system prompt for the conscious LLM
 └──────────┘
      │
      ▼  (system prompt)
 ┌──────────┐
 │  cortex  │  Mina's conscious voice. Receives system prompt, generates user-facing reply.
 └──────────┘
      │
      ▼  (reply)
 USER

Side channel:
 ┌─────────────┐
 │ hippocampus │  Long-term memory. KAG (knowledge files) + RAG (episodic).
 └─────────────┘  Read by decoder (context). Written by memory consolidation (heartbeat).
```

This is the architecture. Every module name should be legible from this diagram.

---

## Target File Structure

```
mina/
  # --- Infrastructure ---
  config.py          # PROJECT_ROOT, all path constants, load_config(), env vars (MODEL, API_KEY)
  client.py          # get_client() — single shared LLM client singleton

  # --- Core simulation ---
  chemicals.py       # REGISTRY: ChemicalProfile, decay rates, interactions, units (unchanged)
  state.py           # BiologicalState dataclass, advance(), apply_deltas(), load/save/log
  vitals.py          # Derived vital signs: heart rate, BP, respiration (unchanged in role)

  # --- The signal pipeline ---
  encoder.py         # External events → neurochemical deltas
  decoder.py         # Neurochemical state → system prompt prose
  cortex.py          # Mina's conscious voice — the user-facing LLM turn
  hippocampus.py     # Long-term memory: KAG, RAG, identity, memory consolidation

  # --- Supporting ---
  observations.py    # Mina's current working state of mind (was: monologue.py)
  tools.py           # Tool definitions + dispatcher (sleep, nap, do_action, search, images)
  heartbeat.py       # 60s biological clock tick — advance() on a timer (was: bio_tick_loop in main.py)
  freetime.py        # Mina's autonomous session when no user is present (was: heartbeat.py)
  token_stats.py     # API call cost tracking (unchanged)
  main.py            # CLI entry point only
```

At a `tree` glance: you can see the signal flow as a list of files. `encoder` feeds `state`, `decoder` reads `state` and writes a prompt, `cortex` runs the user-facing turn using that prompt, `hippocampus` holds the long-term context that flows through the whole thing.

---

## Module Definitions

### `encoder.py`
**What it is:** The biological encoding layer. Takes external events (incoming messages, Mina's own responses, physical actions) and translates them into neurochemical deltas that get applied to the simulation.

**Currently lives in:** `subconscious.py` — mixed in with prompt building and memory consolidation.

**Public interface:**
```python
encode_stimulus(state, stimulus_text) -> dict      # incoming message/event → deltas
encode_response(state, response_text) -> dict      # Mina's reply → deltas
evaluate_activity_deltas(state, activity, description) -> dict  # do_action → deltas
```

**Internal contents:**
- `_call_delta_json()` — shared LLM call infrastructure for all three encode functions
- `_apply_saturation()` — quadratic ceiling blunting near soft/hard limits
- `_apply_personality_scaling()` — Big 5 modulation of delta magnitude
- `_load_personality()` — reads personality.json for Big 5 traits
- `_DELTA_FORMAT`, `_EVENT_OVERRIDE_GUIDANCE` — prompt constant strings

**Token stat labels:** `"encode_stimulus"`, `"encode_response"`, `"encode_activity"` (currently `"delta"`, `"delta_response"`, `"delta_do"` — rename these too).

---

### `decoder.py`
**What it is:** The biological decoding layer. Reads neurochemical state and decodes it into English prose — first as a structured biological report, then via an LLM pass that produces the system prompt Mina's conscious layer runs on.

This subsumes `bio_report.py` entirely. The report is only ever used as input to the decoding LLM call. There is no reason for it to be a separate file.

**Currently lives in:** `bio_report.py` (pure Python report) + `subconscious.py` `run_mode1()` (LLM call that uses that report).

**Public interface:**
```python
build_system_prompt(state, history, kag_context, rag_context) -> str
# Generates the full system prompt for the conscious LLM.
# Internally: biological_report(state) → LLM → <observations> + <system_prompt>
# Side effect: writes updated observations to observations.py

biological_report(state) -> str
# Pure Python. Maps chemical values to labeled ranges with prose descriptions.
# Exposed publicly because it's also used as a console diagnostic ([BIO REPORT]).

needs_summary(state) -> bool
# Threshold check used by autonomous.py to decide whether to trigger a heartbeat.
```

**Internal contents:**
- Range tables (`_CLARITY_RANGES`, `_ANXIETY_RANGES`, etc.)
- `_parse_mode1_output()` — XML tag extraction from LLM response
- `_MODE1_SYSTEM` — the subconscious system prompt
- `_VOICE_CONSTRAINTS` — anti-default voice guardrails appended to every system prompt
- `_load_personality_block()` — Big 5 block for the decoder's context
- `_format_state_for_subconscious()` — state → compact text block (shared by encoder too — move to state.py or keep here)

**Token stat label:** `"decoder"` (currently `"mode1"`).

---

### `cortex.py`
**What it is:** Mina's conscious voice. The user-facing LLM turn. Takes the system prompt from the decoder, conversation history, and user input, and produces Mina's response. Also manages the tool loop (sleep, nap, do_action, search, images).

"Cortex" is the obvious anatomical name for conscious cognition and speech production — as legible as hippocampus.

**Currently lives in:** `main.py` (`run_turn()`, `_mina_turn()`, `api_messages()`, history management, history compaction).

**Public interface:**
```python
run_turn(user_input, username, image_b64, image_mime) -> tuple[str, list[str]]
# Full turn: encode stimulus → decode → LLM → encode response → save history.
# Returns (reply_text, image_paths).
# Called by both main.py (CLI) and discord_gateway.py.
```

**Internal contents:**
- `_mina_turn()` — the LLM call loop with tool resolution
- `api_messages()` — assembles the messages array sent to the API
- `load_history()`, `save_history()`, `_compact_history()` — conversation history management
- `touch_last_active()`, `consume_admin_instructions()` — turn bookkeeping

**Token stat label:** `"cortex"` (currently `"main"`).

---

### `hippocampus.py`
**What it is:** Long-term memory. Stores and retrieves what Mina knows and has experienced. Also handles memory consolidation — the freetime process that writes recent conversation into long-term storage.

The hippocampus is responsible for both memory retrieval and consolidation of short-term experience into long-term storage. Both roles live here.

**Currently split across:** `memory.py` (retrieval/storage) + `subconscious.py` `run_mode2()` (consolidation LLM call).

**Public interface:**
```python
# Retrieval (called by cortex.py and autonomous.py before each turn)
build_kag_context() -> str       # Load and format all KAG files as context block
build_rag_context(query) -> str  # Vector search of episodic memory

# Storage
rag_add(text, metadata) -> None  # Add an episodic memory entry
read_kag(filename) -> str        # Read a knowledge file
write_kag(filename, content) -> None  # Write a knowledge file
read_identity(filename) -> str   # Read a permanent identity file (never wiped)

# Consolidation (called by autonomous.py during heartbeat)
consolidate(state, history, kag_context) -> dict
# LLM pass: recent history → new RAG entries + KAG updates
# Returns {reflection_summary, rag_entries, kag_updates}
# Side effect: writes updated observations
```

**Internal contents:**
- ChromaDB client initialization (currently lazy-initialized globals in memory.py)
- `_MODE2_SYSTEM` prompt constant
- `_parse_mode2_output()`, `_parse_json_robust()`, `_extract_tag()` XML/JSON parsing

**Token stat label:** `"hippocampus"` (currently `"mode2"`).

---

## Tech Debt Inventory

### 1. No package structure — everything flat in root

All source files live directly in the project root alongside config files, state files, and data. There's no `src/` directory, no packages.

**Action:** Move source files to a flat `src/` directory (not a nested package — simpler import story). Or, if a proper package is desired, `src/mina/` with `__init__.py`. The flat `src/` approach is faster and less disruptive.

---

### 2. `MODE_1` / `MODE_2` — opaque names

`subconscious.py` exposes `run_mode1()` and `run_mode2()`. These names are meaningless without reading the code.

**Resolved by:** splitting subconscious.py into `decoder.py` (`build_system_prompt`) and `hippocampus.py` (`consolidate`). The mode numbers disappear entirely.

---

### 3. `tools.py` — dead prototype code

`tools.py` is a leftover from the earliest version of the project. It has stub implementations of `get_current_time`, `calculate`, and `get_weather` (weather is a hardcoded fake string). It exports `TOOLS` and `call_tool` — same names as `tools_mina.py`. It is not imported anywhere.

**Action:** Delete.

---

### 4. `monologue.py` — name/content mismatch

The module is named `monologue.py` but the docstring and git history both confirm the content was renamed to "observations." The file it manages is `run/monologue.md`.

**Action:** Rename to `observations.py`. Rename `_MONOLOGUE_FILE` to `_OBSERVATIONS_FILE`. Runtime file becomes `run/observations.md`.

---

### 5. `_load_config()` duplicated in 5 files

`main.py`, `state.py`, `chemicals.py`, `tools_mina.py`, `heartbeat.py` all define identical `_load_config()` functions.

**Action:** Extract to `config.py`. One implementation, all callers import from there.

---

### 6. `_PROJECT_ROOT` duplicated everywhere

```python
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
```

This appears in every file and is used to build paths to config, state, and runtime files.

**Action:** Centralize in `config.py`. Export `PROJECT_ROOT` and canonical path constants (`STATE_FILE`, `CONFIG_FILE`, `RUN_DIR`, etc.).

---

### 7. LLM client and model config duplicated in 4 files

`main.py`, `subconscious.py`, `heartbeat.py`, `tools_search.py` each independently read `MODEL`, `BASE_URL`, `API_KEY` and define their own `_get_client()`.

**Action:** Extract to `client.py`. One client, one place to swap the model.

---

### 8. `subconscious.py` is the wrong abstraction

989 lines. It mixes the signal encoder, the state decoder, and the memory consolidator into one file under a name that doesn't describe any of them precisely.

**Action:** Replace with `encoder.py`, `decoder.py`, and `hippocampus.py` as defined above. `subconscious.py` is deleted.

---

### 9. `main.py` does too much

CLI entry point, core turn logic, history management, background loops — all in one file.

**Action:** 
- `cortex.py` takes `run_turn()`, `_mina_turn()`, `api_messages()`, history management
- `heartbeat.py` takes `bio_tick_loop()` — the 60s biological pulse
- `main.py` becomes CLI only

---

### 10. Tool file naming is inconsistent

`tools_mina.py` and `tools_search.py` use underscores as a fake namespace.

**Action:** Merge into a single `tools.py` (after deleting the dead prototype `tools.py`). Both tool sets (actions + search) live in one file with a unified dispatcher. If they grow large enough to split, use `tools/` package — but not yet.

---

### 11. "Heartbeat" naming is inverted

`heartbeat.py` is the 30min autonomous session — but the actual biological heartbeat is the 60s deterministic bio tick (`bio_tick_loop()` buried in `main.py`). The names are backwards.

**Action:**
- `heartbeat.py` (30min autonomous session) → `freetime.py`
- `bio_tick_loop()` in `main.py` → extracted to `heartbeat.py`. It *is* the heartbeat: a regular pulse that advances the biological simulation forward in time.

---

### 12. `bio_report.py` — absorbed into `decoder.py`

`bio_report.py` is only ever used as an intermediate step inside the decoder pipeline. Exposing it as a standalone file implies it has an independent role it doesn't have.

**Action:** Fold into `decoder.py`. `biological_report()` remains a public function for diagnostics.

---

## Priority Order

1. **Delete `tools.py`** — no risk, removes name collision immediately
2. **Rename `monologue.py` → `observations.py`** — low risk, high clarity
3. **Extract `config.py` + `client.py`** — kills the most duplication, unblocks everything else
4. **Split `subconscious.py` → `encoder.py` + `decoder.py` + `hippocampus.py`** — biggest win
5. **Extract `cortex.py` from `main.py`** — separates CLI from core turn logic
6. **Absorb `bio_report.py` into `decoder.py`** — simplifies the file count
7. **Merge `tools_mina.py` + `tools_search.py` → `tools.py`** — clean naming
8. **Move to `src/`** — structural, do last once internals are clean

---

## Unit Tests

Test the logic that can break silently. LLM calls get mocked at the boundary — everything above the mock is real.

### What to test

#### `state.py` — biological simulation math
The advance/decay logic is pure arithmetic with no external dependencies. If this breaks, every chemical value drifts wrong and nothing downstream catches it.

```python
# tests/test_state.py
def test_apply_deltas_clamps_to_hard_ceiling()
def test_apply_deltas_negative_delta_floors_at_zero()
def test_advance_decays_cortisol_toward_baseline_over_time()
def test_advance_builds_sleep_pressure_while_awake()
def test_advance_clears_sleep_pressure_while_sleeping()
def test_advance_respects_time_compression_factor()
def test_state_roundtrip_serialize_deserialize()
def test_load_state_returns_defaults_when_file_missing()
```

#### `encoder.py` — saturation and personality scaling
These are pure math functions with no I/O. They gate every delta that enters the simulation. Getting them wrong silently corrupts biomarker values.

```python
# tests/test_encoder.py
def test_saturation_drops_delta_to_zero_above_hard_ceiling()
def test_saturation_scales_quadratically_in_soft_to_hard_zone()
def test_saturation_passes_delta_unchanged_below_soft_ceiling()
def test_saturation_does_not_touch_negative_deltas()
def test_personality_scaling_amplifies_cortisol_spike_at_high_neuroticism()
def test_personality_scaling_dampens_cortisol_recovery_at_high_neuroticism()
def test_personality_scaling_identity_when_no_personality_loaded()

# LLM boundary — mock _get_client()
def test_encode_stimulus_applies_returned_deltas_to_state()
def test_encode_stimulus_skips_apply_on_no_external_deltas()
def test_encode_stimulus_returns_empty_on_llm_error()  # must not crash a turn
def test_encode_response_applies_returned_deltas()
def test_evaluate_activity_deltas_passes_activity_and_description_to_llm()
```

#### `decoder.py` — biological report and prompt parsing
`biological_report()` is pure Python. The XML parsing for `<observations>` and `<system_prompt>` tags is critical — bad parsing silently produces empty system prompts.

```python
# tests/test_decoder.py
def test_biological_report_includes_all_chemicals()
def test_biological_report_labels_cortisol_at_known_ranges()
def test_biological_report_reflects_sleeping_state()
def test_parse_mode1_output_extracts_observations_and_prompt()
def test_parse_mode1_output_handles_missing_tags_gracefully()
def test_parse_mode1_output_handles_empty_string()

# LLM boundary
def test_build_system_prompt_prepends_identity_file()
def test_build_system_prompt_appends_voice_constraints()
def test_build_system_prompt_writes_observations_as_side_effect()
def test_build_system_prompt_returns_fallback_when_llm_returns_empty()
```

#### `cortex.py` — message assembly and history management
`api_messages()` is the function that constructs what actually gets sent to the LLM. Bugs here silently corrupt every conversation. History compaction is also critical — if it misfires, context explodes or gets truncated badly.

```python
# tests/test_cortex.py
def test_api_messages_places_single_system_message_first()
def test_api_messages_strips_internal_system_markers()
def test_api_messages_folds_compact_summary_into_system_prompt()
def test_api_messages_appends_state_note_to_last_user_message()
def test_api_messages_handles_multimodal_last_user_message()
def test_compact_history_returns_original_on_llm_error()  # must not lose history
def test_compact_history_produces_single_system_message_plus_recent()
def test_save_history_truncates_at_max()
```

#### `vitals.py` — derived vital signs
Pure formulas. The safety constraint (natural chemistry alone cannot produce fatal readings) is an architectural guarantee — test it explicitly.

```python
# tests/test_vitals.py
def test_heart_rate_resting_is_in_normal_range()
def test_heart_rate_elevated_by_high_norepinephrine()
def test_heart_rate_cannot_reach_dangerous_level_without_substances()
def test_heart_rate_reaches_dangerous_level_with_REMOVED()
```

#### `hippocampus.py` — memory parsing
The JSON parsing for RAG entries and KAG updates is fragile (it handles malformed LLM output). Silent failures here mean memories are never written.

```python
# tests/test_hippocampus.py
def test_parse_json_robust_handles_json_embedded_in_prose()
def test_parse_json_robust_returns_none_on_garbage_input()
def test_parse_mode2_output_extracts_rag_entries()
def test_parse_mode2_output_extracts_kag_updates()
def test_parse_mode2_output_returns_empty_structure_on_missing_tags()
```

#### `tools.py` — action dispatching and sleep window logic
The sleep window check has a midnight-wrap edge case that's easy to break.

```python
# tests/test_tools.py
def test_sleep_window_midnight_wrap_allows_sleep_at_23h()
def test_sleep_window_midnight_wrap_allows_sleep_at_02h()
def test_sleep_window_midnight_wrap_blocks_sleep_at_14h()
def test_sleep_blocked_outside_window_suggests_nap()
def test_handle_do_action_returns_pending_with_activity_and_description()
def test_call_tool_unknown_name_returns_error_string()  # must not raise
```

### What not to test

- `client.py` — trivial singleton factory
- `config.py` — path construction, no logic
- `token_stats.py` — straightforward file I/O
- `observations.py` — thin file read/write wrapper
- `chemicals.py` REGISTRY values — these are constants, not logic

### Test infrastructure

- Use `pytest` + `unittest.mock`
- Mock boundary: `client.get_client()` returns a mock whose `.chat.completions.create()` returns a canned response object
- Use `tmp_path` (pytest fixture) for any test that reads/writes files — never touch real `run/` or `state.json`
- No test should require a running LLM, ChromaDB, or Discord connection

---

## Verification Checklist

Run these after the refactor is complete, in order.

### Imports and structure
- [ ] `python -c "from cortex import run_turn"` succeeds
- [ ] `python -c "from encoder import encode_stimulus"` succeeds
- [ ] `python -c "from decoder import build_system_prompt, biological_report"` succeeds
- [ ] `python -c "from hippocampus import build_kag_context, consolidate"` succeeds
- [ ] `python -c "from state import BiologicalState, load_state, save_state"` succeeds
- [ ] No circular imports (run `python -c "import cortex"` and watch for ImportError)

### Tests pass
- [ ] `pytest tests/ -v` — all tests green
- [ ] No test hits the real filesystem outside `tmp_path`
- [ ] No test makes a real LLM call

### Runtime smoke test
- [ ] `python main.py` starts without error, prints the CLI header
- [ ] Typing a message produces a response (requires real API key)
- [ ] `/state` command prints the biological state
- [ ] `/reset` completes without error

### State integrity
- [ ] `state.json` still loads correctly after refactor (schema version unchanged)
- [ ] `run/observations.md` is read and written correctly (renamed from monologue.md)
- [ ] `run/conversation.json` is unaffected

### Dashboard
- [ ] Dashboard `/api/state` still returns valid JSON
- [ ] Dashboard `/api/monologue` endpoint updated to read `run/observations.md` (one-line fix)
- [ ] Dashboard `/api/tokens` still returns token stats

### Discord gateway
- [ ] `discord_gateway.py` import of `run_turn` updated from `main` to `cortex`
- [ ] Bot connects and responds to a test message

---

## Open Questions

- Should `derived()` from `state.py` move to `decoder.py` (it's used primarily for report generation) or stay in `state.py` (it's a property of the state)? Currently called from both `bio_report.py` and `subconscious.py`.
- `discord_gateway.py` imports `run_turn` from `main.py` — trivial to update to `cortex.py`, just needs tracking.
- When `autonomous.py` calls the decoder and encoder, it follows the same pipeline as a normal turn. Should the pipeline be formally extracted (e.g., `pipeline.py`) or is calling them in sequence from `cortex.py` / `autonomous.py` sufficient? Probably sufficient for now.
