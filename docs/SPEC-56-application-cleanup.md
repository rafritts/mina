# SPEC-56: Application Cleanup Pass

**Status: TODO**

---

## Problem

The codebase has accumulated technical debt from successive spec implementations: broken imports, dead fields, duplicate state I/O implementations, legacy constants never cleaned up, and compat shims that outlived their purpose. This spec is a focused cleanup pass — no behavior changes, no new features.

Everything here is either a latent bug, dead code confirmed unused, or a two-source-of-truth situation that will cause a real bug when someone tunes the wrong copy.

---

## Changes

### 1. Fix broken imports in `memory_triggers.py` — CRITICAL

`src/engine/memory_triggers.py` lines 55 and 71 use bare-path imports:
```python
from hippocampus import rag_add
```
These will fail at runtime. Every call to `process_events()` silently swallows the `ImportError`, meaning biological significance events are never persisted to RAG. Fix:
```python
from src.brain.hippocampus.hippocampus import rag_add
```

---

### 2. Unify `load_state` / `save_state`

Two separate implementations exist:
- `src/brain/brainstem/state.py` — atomic write (`.tmp` file), wraps `config._STATE_FILE`
- `src/engine/bio/persistence.py` — direct (non-atomic) write, defines its own `_STATE_FILE`

`brainstem/state.py` is the better implementation (atomic writes prevent partial writes on crash). The fix:
- Delete `persistence.py`
- Update all callers of `persistence.py`'s `load_state`/`save_state` to import from `brainstem/state.py`
- Confirm the file path resolution is identical in both

---

### 3. Delete the `habituation` field from `BiologicalState`

`src/engine/bio/state.py` line 94:
```python
# habituation: renamed from encoder_momentum (SPEC-29); retained for migration compat but no longer used.
habituation: dict = field(default_factory=dict)
```
Never read or written after migration. Safe to delete. Remove the field from `state.py` and from `migration.py`'s `migrate_v3_to_v4()`.

---

### 4. Delete `compact_history_if_needed()` from `cortex.py`

`src/brain/cortex/cortex.py` lines 728–730:
```python
async def compact_history_if_needed() -> None:
    """No-op — compaction replaced by RAG aging in SPEC-27. Kept for gateway compat."""
    pass
```
It does nothing. Remove it from `cortex.py` and remove the call from `discord_gateway.py`.

---

### 5. Delete dead constants

Remove from `src/engine/constants.py`:
- `SLEEP_PRESSURE_BUILD_RATE` — marked "legacy", no references in codebase
- `ADENOSINE_SEROTONIN_DRAIN_THRESHOLD` — references "legacy sleep_pressure scale", no references
- `MELATONIN_AUTO_SLEEP_LEGACY_THRESHOLD` — "kept for backward compat", no references
- `HISTORY_KEEP` alias in `src/brain/cortex/cortex.py` (line 80) — assigned but never read

---

### 6. Use constants for `sleep_pressure` calculation in `BiologicalState`

`src/engine/bio/state.py` lines 150–151:
```python
raw = (self.body["adenosine"] - 20.0) / 0.60
```
The magic numbers `20.0` and `0.60` are already defined in `constants.py` as `ADENOSINE_SLEEP_DRIVE_MIN` and `ADENOSINE_SLEEP_DRIVE_DIVISOR` but not imported here. Fix: import and use the constants.

---

### 7. Remove `brainstem/chemicals.py` compat shim

`src/brain/brainstem/chemicals.py` is a pure re-export shim — it imports everything from `src.engine.chem.*` and re-exports it. There are 5 active callers:
- `src/brain/subconscious/decoder.py`
- `src/brain/amygdala/stimulus_encoder.py`
- `src/application/gateway/discord_gateway.py`
- `src/application/infra/dashboard.py` (if present)
- others if found

Update each caller to import directly from `src.engine.chem.registry` or `src.engine.chem.units`, then delete `brainstem/chemicals.py`.

---

### 8. Remove legacy tolerance scalar from dopamine reward calculation

`src/engine/psych/derived.py` lines 237–241 still apply `s.tolerance.get("dopamine", 0.0)` as a multiplier in the dopamine reward calculation, marked "kept for backward compat during transition."

The biologically correct mechanism is receptor downregulation — when D2 receptors are chronically flooded, receptor density and affinity decrease. That is exactly what `receptor_sensitivity["dopamine"]["D2"]` models. The old scalar is a simplified pre-receptor abstraction.

Fix: remove the `tol_d` multiplication from the dopamine reward math in `derived.py`. The `s.tolerance` dict itself is retained — the substance system (alcohol, caffeine) still uses it for substance-level tolerance tracking. Only the dopamine reward calculation is changed.

---

### 9. Delete `build_memory_context()` shim in `decoder.py`

`src/brain/subconscious/decoder.py` has a legacy shim:
```python
def build_memory_context(...) -> str:
    """Legacy shim — kept for freetime/consolidation callers. Delegates to build_rag_context."""
    return build_rag_context(query, kag_context, rag_recent, "", rag_historical)
```
Two callers: `freetime.py` and `followup.py`. Update both to call `build_rag_context` directly, then delete the shim.

---

### 10. Fix `TODO SPEC-22` comment in `engine.py`

`src/engine/engine.py` line 490:
```python
# TODO SPEC-22: extend for neuroendocrine tier targets
```
SPEC-22 is done. Either this work was completed (remove the comment) or it was intentionally deferred (move to a new spec). Investigate and resolve.

---

## What This Is NOT

- No behavior changes
- No architectural restructuring of decoder.py or hippocampus.py (separate scope)
- No new features or tuning
- No changes to the chemical registry or profiles

---

## Files Touched

| File | Change |
|------|--------|
| `src/engine/memory_triggers.py` | Fix broken bare imports (item 1) |
| `src/engine/bio/persistence.py` | **Delete** — replaced by brainstem/state.py (item 2) |
| `src/engine/bio/state.py` | Remove `habituation` field; use constants in `sleep_pressure` (items 3, 6) |
| `src/engine/bio/migration.py` | Remove `habituation` rename from migrate_v3_to_v4 (item 3) |
| `src/brain/cortex/cortex.py` | Delete `compact_history_if_needed`; delete `HISTORY_KEEP` alias (items 4, 5) |
| `src/application/gateway/discord_gateway.py` | Remove call to `compact_history_if_needed` (item 4) |
| `src/engine/constants.py` | Delete 3 dead constants (item 5) |
| `src/brain/brainstem/chemicals.py` | **Delete** — update 5 callers first (item 7) |
| `src/engine/psych/derived.py` | Resolve tolerance scalar (item 8) |
| `src/brain/subconscious/decoder.py` | Delete `build_memory_context` shim (item 9) |
| `src/brain/subconscious/freetime.py` | Update to call `build_rag_context` directly (item 9) |
| `src/brain/cortex/followup.py` | Update to call `build_rag_context` directly (item 9) |
| `src/engine/engine.py` | Resolve TODO SPEC-22 comment (item 10) |
