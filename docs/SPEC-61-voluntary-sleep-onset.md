# SPEC-61 — Voluntary Sleep Onset (Settling Countdown)

**Status:** Draft — needs sign-off before implementation  
**Date:** 2026-08-06  
**Depends on:** sim sleep flag (`Sim._sleeping`), FREETIME `sleep` tool, adenosine auto-sleep, scene context, UI presence

---

## Problem

Humans do not flip from fully awake to asleep in one bit flip. When tired, a person can **choose** to go to bed: take layers off, flop down, stop moving, dim the lights — a voluntary wind-down with sleep latency. Only after that countdown do they actually sleep. Forced collapse (nodding off upright) is a different path.

Mina today has only **binary sleep**:

| Path | What happens |
|------|----------------|
| Auto-sleep | Adenosine ≥ `SLEEP_ENTER_ADENOSINE` (8.0) → `_sleeping = True` immediately |
| FREETIME `sleep` tool | `sim.set_sleeping(True)` immediately — same binary flag |
| Chat tools | No sleep tool at all |
| Persistence | `_sleeping` is **not** saved with `sim_state.json` (restart = always awake) |

There is **no** intermediate state for “I decided to go to bed and I’m settling.”  
There is **no** countdown / latency.  
There is **no** voluntary behavioral sequence distinct from crash sleep.

v1 was the same idea with more gates (sleep window, nap blackout) still landing on instant `state.sleeping = True`.

---

## Goal

Give Mina a **voluntary sleep-onset path**:

1. She feels tired enough (or chooses rest) via felt state / FREETIME / chat.
2. She **initiates** going to bed (tool + scene).
3. She enters a **settling** phase — still conscious, low activity, countdown running.
4. When the countdown completes (and nothing interrupts hard enough), she becomes **asleep**.
5. Auto-sleep remains the involuntary crash path when adenosine is extreme.

Observable difference: UI/presence, FREETIME cadence, chemistry recovery timing, and narrative scene should all distinguish **settling** from **asleep**.

---

## Non-goals

- Full sleep-stage architecture (N1/N2/N3/REM) — overshoot past B+.
- Clock-only “bedtime window” as the sole gate (v1-style hour lock). Chemistry + choice lead; clock may bias, not hard-block.
- Forcing every high-adenosine path through a long ritual when she is already past the edge of collapse.
- Multi-agent “tuck her in” gameplay unless it falls out of chat naturally.

---

## Consciousness states

Replace the single boolean with an explicit state machine on the sim (still cheap to query):

```
awake ──(voluntary sleep tool)──► settling ──(countdown done)──► asleep
  ▲                                  │                              │
  │                                  │ interrupt                    │ wake criteria
  │                                  ▼                              │
  └────────────── awake ◄────────────┘                              │
  ▲                                                                 │
  └────────────────────────────── awake ◄───────────────────────────┘

awake ──(adenosine crash)──► asleep     # optional short/no settle — see below
```

### State semantics

| State | Consciousness | FREETIME | Chat | Adenosine clear | Presence label |
|-------|---------------|----------|------|-----------------|----------------|
| `awake` | Full | Normal cadence | Normal | No (accumulates) | existing presenceLabel |
| `settling` | Yes — wind-down | Sparse or skip active tools that raise arousal; diary OK | Responsive but soft / brief preferred | Mild assist (see chemistry) | **Settling** / **Going to sleep** |
| `asleep` | No active free-time | Skip (current behavior) | Can still land messages (wake / groggy policy later) | Full sleep clear (current tick behavior) | **Sleeping** |

API / UI:

```json
{
  "sleeping": false,
  "consciousness": "settling",
  "settle": {
    "started_at": 1722…,
    "ends_at": 1722…,
    "reason": "heavy and done for the night"
  }
}
```

Keep `sleeping: true` **only** for `asleep` so existing clients stay correct. Add `consciousness` as the full enum. Deprecate reading sleep only from `sleeping` once UI migrates (UI should prefer `consciousness`).

---

## Voluntary path (the countdown)

### Trigger

**Primary:** FREETIME tool `sleep` (exists today — change behavior).

**Secondary (same handler):** optional chat-available tool or mouth JSON intent later. v1 of this spec ships FREETIME + any shared `begin_sleep_onset(sim, reason=…)` so chat can call the same code without duplicating logic.

Tool contract (updated):

```text
name: sleep
description: Decide to go to bed / nap. Starts a wind-down (settling), not instant
  unconsciousness. Use when you feel ready to rest — heavy, drowsy, or choosing bed.
parameters:
  reason?: string
  intent?: "night" | "nap"   # optional; nap → shorter latency
```

Handler **must not** call `set_sleeping(True)` immediately.

### Settling duration

Real wall-clock (or sim `dt` — pick one and stick to it; **prefer wall-clock** so advancing sim hours in admin does not skip a 20‑minute human-scale wind-down unless we also advance settle remaining).

| Intent | Default latency | Bounds |
|--------|-----------------|--------|
| `night` | 20 min | 10–45 min |
| `nap` | 8 min | 5–20 min |

**Modulation (optional, keep light):**

- Higher adenosine / lower orexin → shorter latency (she falls in faster).
- Recent high arousal (NE/epi phasic) → slightly longer latency or soft refuse (“too wired — settle first”).
- Extreme adenosine (≥ auto-sleep enter): tool may short-circuit to `asleep` or a 1–2 min settle (crash).

Constants live in `src/sim/params.py` next to existing sleep thresholds.

### What happens during settling

1. **State:** `consciousness = settling`; store `settle_ends_at`, `reason`, `intent`.
2. **Scene (soft, not mandatory on tool alone):** next mouth/FREETIME turn should re-author scene toward bed (clothing layers off, position in bed, lights low). Spec does not hard-code outfit strings; pillars/prompt encourage it when settling is active.
3. **Chemistry assist (B+, small):** while settling, tick applies a mild wind-down — not full sleep clear:
   - Slight orexin / NE downward pressure or reduced accumulation
   - Optional small melatonin-compatible bias if circadian is already night-ish
   - Adenosine: **no** full phasic clear (that remains sleep-only); optional slower accumulation or slight phasic relief so settling feels progressive
4. **FREETIME:** `should_fire` returns false for *active* free-time while settling **or** allows only sleep-compatible tools (`record_diary`, not `do_action` exercise). Prefer **skip active FREETIME** during settling to avoid her “going for a run” mid-countdown.
5. **Countdown complete:** transition `settling → asleep` (same as current sleep entry: `_sleep_elapsed_s = 0`, log `Sleep ON (onset complete)`).
6. **UI:** presence shows Settling; Control Consciousness card shows countdown remaining.

### Interrupts

While `settling`:

| Event | Effect |
|-------|--------|
| User chat (any turn) | **Does not auto-cancel.** She can talk from bed. Settling continues unless she aborts or high-arousal chemistry spikes. |
| Explicit abort | New tool `wake` / `cancel_sleep` or `sleep` with `cancel: true` → back to `awake`, clear settle timer. |
| Auto-sleep threshold while settling | Accelerate: jump to `asleep` immediately (pressure won). |
| Admin reset / chemistry reset | Clear settle + awake (current reset wakes). |
| Process restart | **Persist** consciousness + settle ends_at (see Persistence). |

High-arousal interrupt (optional phase 2): encoder deltas that spike NE/epi hard during settling can extend latency or cancel — defer if it complicates v1.

---

## Involuntary path (auto-sleep)

Keep adenosine crash:

- `ade >= SLEEP_ENTER` while `awake` → enter `asleep` **directly** (collapse), **or** enter a **short** settle (≤2 min) for narrative softness.
- **Recommendation for v1:** direct `asleep` on crash so recovery still works when FREETIME is skipped near threshold; voluntary path is the human-like one; crash stays physiological.

Wake criteria unchanged: min sleep duration + adenosine ≤ `SLEEP_WAKE`.

---

## Persistence

Today sleep is RAM-only. Fix as part of this work:

In `sim_state.json` (alongside chemical levels):

```json
{
  "levels": { ... },
  "consciousness": "settling",
  "sleep_elapsed_s": 0,
  "settle": {
    "ends_at": 1722.0,
    "started_at": 1720.0,
    "reason": "...",
    "intent": "night"
  }
}
```

Load on Sim init; save on existing save cadence. If `settling` and `ends_at` is already past at load → complete to `asleep` (or recompute remaining).

---

## Prompt / pillar surface

Mina must not read raw chemistry, but she **should** feel settling via insula/PFC when the state is active:

- Inject a short line into free-time synthetic message and/or mouth system context when `consciousness == settling`:
  - e.g. “You decided to go to bed. You are settling — still half-aware, winding down. Sleep is coming soon.”
- Insula: allow mild drowsiness language during settling even if adenosine is not yet “ferocious” — settling is **behavioral**, not only chemical. Gate: if `settling`, false-sleepiness nudge does **not** strip bed/wind-down language.
- Scene contract: when settling, encourage clothing/position toward sleep.

Do **not** dump countdown seconds into the mouth prompt (instrumentation smell). Soft phrases only (“almost under” when &lt;5 min left is OK if derived host-side).

---

## API & UI

### Backend `GET /api/state` (and stream snapshots)

```json
{
  "sleeping": false,
  "consciousness": "settling",
  "settle": {
    "remaining_s": 842,
    "ends_at": 1722.0,
    "reason": "heavy and done for the night",
    "intent": "night"
  }
}
```

### UI

- Chat/Lab status pill: `Settling` (reuse or extend `sleep` tone; optional distinct dimmer blue).
- Control → Consciousness card: Awake / Settling (with mm:ss remaining) / Asleep.
- `presenceLabel`: Settling before other affect labels when `consciousness === 'settling'`.

No need for a manual “force settle” control in v1 (advance time + high ADE already tests crash; tool tests voluntary).

---

## Code touch map (implementation outline)

| Area | Change |
|------|--------|
| `src/sim/sim.py` | State machine; `begin_settling`, `cancel_settling`, tick settle countdown; persist fields |
| `src/sim/params.py` | Latency defaults/bounds, optional chemistry assist rates |
| `src/sim/tick.py` | Mild settling chemistry branch when not fully asleep |
| `src/freetime/tools.py` | `handle_sleep` → begin settling; optional `wake`/`cancel_sleep` |
| `src/freetime/freetime.py` | Skip or constrain FREETIME while settling; inject settle line in synthetic message |
| `src/brain/insula.py` | Don’t strip sleep language while settling |
| `src/gateway/server.py` | Expose consciousness + settle in `_build_state` / stream |
| `ui/...` | presence, Control card, header status |
| `tests/` | onset → asleep; interrupt cancel; crash path; persistence across load |

---

## Acceptance criteria

1. Calling FREETIME `sleep` does **not** set `sleeping=true` immediately; `consciousness` becomes `settling`.
2. After configured latency with no cancel, state becomes `asleep` and adenosine clear behaves as today.
3. UI shows Settling with remaining time; when asleep, Sleeping (existing).
4. Auto-sleep at high adenosine still recovers monoamines (existing tests pass; new tests for settling path).
5. Restart mid-settle preserves remaining time (or completes if elapsed).
6. FREETIME does not run arousal-heavy activities during settling.
7. Chat while settling remains possible; she is not hard-offline.

---

## Open questions (resolve at sign-off)

1. **Wall-clock vs sim-time for latency?** Recommendation: wall-clock for settle; sim-time for auto-sleep min duration (already dt-based).
2. **Chat tool for sleep in v1?** Recommendation: shared sim API only in FREETIME first; chat can follow if she needs to “go to bed” mid-conversation via tool.
3. **Crash path settle buffer (0 vs 1–2 min)?** Recommendation: 0 for v1.
4. **Nap vs night intents in tool?** Nice-to-have; single default latency is enough for first cut.
5. **Should user messages extend settle (talking keeps her up)?** Recommendation: no auto-extend in v1; she can cancel or the countdown finishes while she chats in bed.

---

## Relationship to current code (audit summary)

| Existing piece | Role after this spec |
|----------------|----------------------|
| `Sim._sleeping` / `is_sleeping` / `set_sleeping` | Map to `asleep` only; add settling APIs |
| Auto-sleep adenosine gates | Unchanged crash path |
| FREETIME `sleep` tool | Entry to **settling**, not instant sleep |
| FREETIME skip when sleeping | Also skip (or constrain) when settling |
| UI `sleeping` flag | Keep; add `consciousness` + settle remaining |
| Insula ferocious-adenosine gate | Exception while settling |

---

## Implementation order (after sign-off)

1. Sim state machine + persistence + tick countdown  
2. FREETIME tool + cadence + synthetic message  
3. Gateway payload  
4. UI presence / Control  
5. Insula / scene prompt nits  
6. Tests  

Do not implement until this draft is accepted (or amended) explicitly.
