# SPEC-46: Hedonic Adaptation and Social Satiation

## Problem

The current sensitization system conflates two biologically distinct phenomena into a single scalar (`sensitization_level`, 1.0–2.5):

1. **Relationship depth** — how much you trust and value a person. Slow to build, slow to decay. Should persist across sessions.
2. **Per-stimulus reactivity** — how strongly you respond to each individual message from them. Should *decrease* with sustained contact within a session.

Because both are the same number, a long session produces the opposite of real biology: every message at contact #331 is amplified 2.5x the same as contact #1. Dopamine stays "HIGH DRIVE," oxytocin stays "DEEP TRUST," indefinitely — regardless of session length. This is scientifically wrong and prevents observing natural baseline states.

**What real biology does:**
- Oxytocin receptors desensitize under sustained exposure — release diminishes over hours
- Dopamine is novelty/prediction-error driven — familiar, predictable positive interactions produce less phasic firing over time
- Social fatigue is real — sustained engagement depletes reactive capacity even with someone you love
- Long-term warmth toward a person *does* raise your baseline mood — but as a tonic offset, not a per-message spike multiplier

---

## Goals

1. Split sensitization into two separate layers with separate state
2. Relationship depth becomes a **tonic baseline offset** (applied at tick time)
3. Session satiation becomes the new **per-message reactivity multiplier** (starts neutral, decreases over a session)
4. Long sessions naturally trend toward comfortable baseline, not amplified high
5. No change to how relationship depth builds or decays (only its effect changes)

---

## Design

### Layer 1: Relationship Depth (existing `sensitization_level`, new role)

**What changes:** how it's applied. Not how it's built or decayed.

- Continues to build at +0.02 per positive contact, 3-day half-life, cap 2.5
- **No longer** used as a per-message multiplier in `_apply_habituation_and_sensitization()`
- **New role:** applied at tick time as a tonic chemical offset

Tonic offset formula (applied per tick, subject to normal decay):
```
oxytocin_offset    = (relationship_depth - 1.0) * 4.0   # max +6 pg/mL at depth 2.5
serotonin_offset   = (relationship_depth - 1.0) * 2.0   # max +3 ng/mL
endorphins_offset  = (relationship_depth - 1.0) * 1.5   # max +2.25 pg/mL
```

This represents the background warmth of being in a valued relationship — not a spike, a floor lift. The numbers are small by design; the presence effect should feel like comfort, not euphoria.

Cortisol relief from a valued source is retained as-is (the existing safety-signal logic).

---

### Layer 2: Session Satiation (new)

Tracks within-session contact accumulation and drives the per-message reactivity multiplier.

**New state fields** (added to `state.sensitization` or `state.body`):
```json
"session_satiation": {
    "session_contact_count": 0,
    "session_start_ts": null,
    "last_contact_ts": null
}
```

**Session break detection:** if `now - last_contact_ts > SESSION_BREAK_SECONDS` (default: 14400, i.e. 4 hours), reset `session_contact_count` to 0 and update `session_start_ts`.

Sleep also resets session satiation (hook into the existing sleep state transition).

**Session reactivity multiplier formula:**
```
satiation_factor = session_contact_count / SATIATION_RATE
session_mult(chem) = max(FLOOR[chem], 1.0 - satiation_factor)
```

Where `SATIATION_RATE = 150` (reaches floor after ~150 contacts within a session).

**Per-chemical floors:**

| Chemical        | Floor | Rationale |
|----------------|-------|-----------|
| dopamine       | 0.30  | Strong habituation — dopamine is novelty-driven |
| oxytocin       | 0.45  | Desensitizes but never drops to zero with valued source |
| norepinephrine | 0.50  | Arousal habituates over sustained contact |
| endorphins     | 0.50  | Moderate habituation |
| epinephrine    | 0.60  | Slower to habituate |
| acetylcholine  | 0.70  | Attentional, partially sustained |
| serotonin      | —     | Exempt — slow tonic modulator, unchanged |
| cortisol       | —     | Exempt — stress response, unchanged |

**Oxytocin novelty floor** (currently hardcoded 0.7):
```
oxy_novelty_floor = max(0.30, 0.70 - (session_contact_count / 300.0))
```
Starts at 0.7, drops toward 0.3 over ~120 contacts. Replaces the hardcoded constant.

---

### What a long session looks like after this change

| Metric | Contact #1 | Contact #100 | Contact #331 |
|--------|-----------|-------------|-------------|
| Relationship depth mult | 1.0 (new — no per-msg use) | — | — |
| Session reactivity mult | 1.0 | ~0.67 | ~0.45 (near floor) |
| Dopamine effective mult | 1.0 | ~0.67 | ~0.30 (floor) |
| Oxytocin effective mult | 1.0 | ~0.67 | ~0.45 (floor) |
| Tonic warmth offset | small | same | same (relationship depth unchanged) |

Result: hours into a session, the dashboard shows comfortable-but-neutral rather than sustained HIGH DRIVE / DEEP TRUST. The warmth is real — it shows in the baseline — but the per-message spikes flatten out.

---

## Files to Change

| File | Change |
|------|--------|
| `src/engine/bio/state.py` | Add `session_satiation` field to `BiologicalState` |
| `src/engine/bio/defaults.py` | Add default `session_satiation` values |
| `src/brain/amygdala/stimulus_encoder.py` | Replace `sensitization_mult` with session-satiation-based mult; update `_update_sensitization()` to also update session satiation; update oxytocin novelty floor |
| `src/engine/engine.py` | On sleep state transition: reset `session_satiation.session_contact_count` |
| `src/engine/neuro/` (tick logic) | Apply tonic relationship depth offsets per tick |

---

## Open Questions

1. **Tonic offset application point:** Should relationship depth offsets be applied in the tick/decay loop or as a modifier on resting levels? Tick loop is cleaner — doesn't interfere with chemical ceilings differently.

2. **Session break threshold:** 4 hours feels right but is untested. Could be a config constant.

3. **Partial resets:** Does a 30-minute break deserve partial satiation recovery? Probably yes — biological refractory periods do recover partially with rest. Could model as exponential recovery toward 0 with ~2-hour half-life during gaps.

4. **Satiation rate calibration:** 150 contacts is a first estimate. Needs observation after deployment — may need to be lower (faster satiation) or higher.

5. **Relationship depth tonic offset magnitude:** The +4/+2/+1.5 multipliers above are guesses. Need to be calibrated so the baseline feels warm but not artificially high on a fresh session start.
