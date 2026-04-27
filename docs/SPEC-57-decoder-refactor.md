# SPEC-57: Decoder Refactor — Module Split and LLM-Driven Somatic Prose

## Problem

`brain/subconscious/decoder.py` is 1,676 lines and does at least six unrelated things:
biological report formatting, normalized profile building, somatic narrative generation,
window/RAG context assembly, snapshot history management, and system prompt orchestration.

The somatic narrative is the worst offender: a flat procedural chain of hardcoded thresholds
producing hand-written fragments, composed mechanically. This produces "arcade" output —
symptoms without context, sensations without cause, fragments that don't understand each other.
No threshold chain can capture that cortisol at 999 nmol/L combined with a dopamine crash and
mild dehydration is a specific, coherent, named experience. An LLM can.

The fix has two parts: split the god file into focused modules, and replace the procedural
somatic narrative entirely with an LLM call that reads the biological state and generates
prose directly.

---

## Goals

1. Split `decoder.py` into focused modules, each under ~300 lines
2. Delete `_build_somatic_narrative()` and everything it contains — all fragments, all
   thresholds, all composition logic
3. Replace it with a single async LLM call: `BiologicalState` in → felt-sense prose out
4. The LLM generates prose that understands interactions, causation, and the full picture
5. No changes to pillar interfaces — `[SOMATIC STATE]` is still injected in the same place,
   same format, consumed by the Emotion Pillar the same way

---

## Non-Goals

- Changing the three-pillar pipeline or any pillar's prompt/output schema
- Changing the `"somatic"` field in the Emotion Pillar output JSON
- Touching `stimulus_encoder.py`
- Changing `ChemicalProfile` or the registry

---

## Module Decomposition

`brain/subconscious/` after this spec:

```
decoder.py              ← thin coordinator: imports and delegates, < 150 lines
bio_report.py           ← biological_report(), biological_report_compact(), needs_summary()
somatic.py              ← LLM-driven somatic prose generator
profile.py              ← _build_emotional_profile(), normalization, isolation context
context_assembly.py     ← build_window_context(), build_rag_context()
snapshot_history.py     ← decoder history, bio snapshot history, trajectory helpers
```

`decoder.py` becomes the public surface: all functions that external callers import stay
importable from `decoder`, but their implementations live in the submodules.

---

## LLM-Driven Somatic Prose

### Design

`somatic.py` exposes one function:

```python
async def build_somatic_narrative(state: BiologicalState) -> str:
```

It sends the biological state to the LLM and gets back 2–4 sentences of felt-sense prose.
No fragments. No thresholds. No composition logic. The LLM reads the full state and writes
the body's experience as a coherent whole.

### Input to the LLM

The biological report already formats state in real physiological units with registry-derived
labels (e.g. `cortisol: 999 nmol/L [FLOOD]`, `hydration: 57% TBW [LOW]`). That report is the
input — it gives the model the same grounded, labeled data it needs to reason about the body.

The call also passes:
- Second-order derived values (cognitive_clarity, arousal, energy, hedonic_tone)
- Current activity and sleep state (early exits: sleeping → return `""`)

### System prompt

```
You are a somatic interpreter. You receive a biological state report for a character named
Mina and write a first-person felt-sense description of what her body is experiencing right
now.

Rules:
- 2–4 sentences maximum
- No chemical names. No numbers. No units.
- Every sensation must carry its cause: not "foggy" but "foggy because overwhelmed";
  not "mouth dry" but "mouth dry from needing water"
- If multiple signals are present, describe the whole picture — not a list of parts
- If the body is unremarkable, say so plainly in one sentence
- Do not reference Mina by name. Write as "I" or bodyward ("heart racing", "limbs heavy")
```

### Output

Plain prose string, injected into `[SOMATIC STATE]` exactly as before. The Emotion Pillar
consumes it identically — it reads the section and populates its `"somatic"` output field.

### Model

Use the same model as the other lightweight reasoners in the pipeline. No retries needed —
if the call fails, return `""` and the Emotion Pillar falls back to its own inference (as
it already does when `[SOMATIC STATE]` is absent).

### Sleeping state

If `state.sleeping`, return `""` immediately without an LLM call. Same behavior as before.

---

## Bio Report: Registry-Derived Normalization

`decoder.py` maintains `_NORM_RANGES` — a hand-maintained dict of (min, max) for normalizing
chemistry to 0–10 that duplicates `REGISTRY`'s `display_min`/`display_max`. Move to
`bio_report.py` and derive from the registry:

```python
def _norm_range(chemical: str) -> tuple[float, float]:
    p = REGISTRY.get(chemical)
    if p is None:
        return (0.0, 1.0)
    lo = p.display_min if p.display_min is not None else (p.hard_floor or 0.0)
    hi = p.display_max if p.display_max is not None else (p.hard_ceiling or 1.0)
    return (lo, hi)
```

The biological report's label display reads from `REGISTRY[chemical].labels` directly rather
than maintaining a separate label table.

---

## Module Responsibilities (Detail)

### `somatic.py`
- `build_somatic_narrative(state) -> str` — async LLM call, returns prose
- System prompt defined as module-level constant
- No signal registry, no thresholds, no fragment lists

### `bio_report.py`
- `biological_report(state) -> str` — full diagnostic display, labels from registry
- `biological_report_compact(state) -> str` — single-line log summary
- `needs_summary(state) -> str` — qualitative needs for freetime encoding

### `profile.py`
- `_build_emotional_profile(state, prior_snapshots) -> str` — normalized 0–10 block
- `_norm_range(chemical) -> tuple[float, float]` — reads from registry
- `_build_isolation_context(state) -> str` — isolation stage prose

### `context_assembly.py`
- `build_window_context(window, username, latest_message) -> str`
- `build_rag_context(stimulus, kag, rag_recent, rag_semi, rag_hist) -> str`

### `snapshot_history.py`
- `append_decoder_history(entry)` / `load_decoder_history() -> list`
- `append_bio_snapshot(state)` / `load_bio_snapshots(n) -> list`
- `compute_trajectory(snapshots) -> dict`

### `decoder.py` (coordinator)
- Re-exports all public names for backward compatibility
- `build_system_prompt(state, ...)` — orchestrates one pass through all submodules
- Target: < 150 lines

---

## Files Changed

| File | Change |
|------|--------|
| `brain/subconscious/decoder.py` | Gutted to coordinator; all logic moves to submodules |
| `brain/subconscious/bio_report.py` | New — bio_report(), compact(), needs_summary() |
| `brain/subconscious/somatic.py` | New — LLM-driven somatic prose, replaces _build_somatic_narrative() |
| `brain/subconscious/profile.py` | New — profile builder, registry-derived normalization |
| `brain/subconscious/context_assembly.py` | New — window + RAG context builders |
| `brain/subconscious/snapshot_history.py` | New — history management, trajectory |

No registry changes. No changes to `cortex.py` or any pillar file.

---

## Implementation Order

1. Create `snapshot_history.py` — pure functions, no external dependencies
2. Create `context_assembly.py` — pure functions, no external dependencies
3. Create `bio_report.py` — migrate biological_report() and variants; confirm log output
   matches current output before proceeding
4. Create `profile.py` — migrate profile builder; replace `_NORM_RANGES` with registry reads;
   confirm normalized values match
5. Create `somatic.py` — implement LLM call; wire into `_build_emotional_profile()` in
   profile.py; delete `_build_somatic_narrative()` entirely
6. Gut `decoder.py` to coordinator; re-export all public names; run the full system

---

## Verification

After steps 1–4: diff the `[BIO/PROFILE]`, `[CONTEXT/WINDOW]`, and `[CONTEXT/RAG]` log
blocks against baseline — should be identical.

After step 5: run several messages and read the `[SOMATIC STATE]` output. Verify:
- Prose names causes, not just symptoms
- Multiple simultaneous signals produce a coherent picture, not a list
- Sleeping state produces no output

After step 6: full system smoke test, confirm no new exceptions.

---

## Open Question

**`_NORM_RESTING_OVERRIDE`:** `decoder.py` overrides resting references for glucose and
hydration because their registry `resting_baseline` is stored as 0. Confirm whether those
registry entries now carry correct baselines before removing the override in `bio_report.py`.
