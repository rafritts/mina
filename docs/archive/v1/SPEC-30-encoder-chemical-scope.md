# SPEC-30: Encoder Chemical Scope

## Overview

The encoder translates external events into neurochemical deltas. Its scope should be limited to **acutely event-responsive chemicals** — ones that spike or drop within minutes of a trigger. Tonic chemicals that reflect chronic background state over days and weeks do not belong in the encoder: they should be driven by the simulation engine's homeostatic machinery and baseline functions.

This spec audits every chemical the encoder currently touches, removes inappropriate ones, tightens guidance on others, and adds two chemicals that are genuinely missing.

---

## Core Principle

> **Encoder = acute signals. Engine = tonic signals.**

A chemical belongs in the encoder if and only if it can meaningfully change within a single event (a message, a hug, a workout). If its timescale is hours-to-days and it reflects a chronic condition rather than a discrete event, it belongs in a `baseline_fn` or subsystem — not in the encoder.

---

## Chemical-by-Chemical Audit

### ✅ Keep as-is

| Chemical | Reason |
|---|---|
| **Cortisol** | Responds acutely to psychological threat and safety signals via HPA. Correct. |
| **Dopamine** | Textbook event-response chemical — novelty, seeking, prediction error. Correct. |
| **Norepinephrine** | Fast arousal/alertness signal. Responds within seconds. Correct. |
| **Oxytocin** | Social bonding events produce real acute release. Correct. |
| **Glucose** | Activity encoder only — eating legitimately changes blood glucose. Correct. |
| **Hydration** | Activity encoder only — drinking changes TBW. Correct. |
| **Sleep pressure** | Legitimately appears for caffeine (activity) and intense physical peak resolution (event override). Correct. |

---

### ❌ Remove from conversation encoding

#### Serotonin

**Problem:** Serotonin is a tonic neuromodulator. It reflects chronic social conditions — social status, sense of belonging, long-term safety — over days and weeks. Individual messages do not acutely spike serotonin. The current encoder posts `serotonin: +0.5–1.2` on nearly every response ("engaged energetic expression"), bypasses habituation by design, and produces continuous accumulation. This is the primary driver of Mina's persistent cloud-9 state.

**Fix:**
1. Remove `serotonin` from `encode_stimulus()` and `encode_response()` entirely.
2. Keep it in `encode_activity()` for the narrow physical cases where it is legitimately event-driven: eating (tryptophan synthesis), exercise, showering.
3. Route chronic social conditions into `_serotonin_baseline_fn` via `isolation_pressure` (already tracked in state). Low isolation pressure (regular contact) supports a higher serotonin baseline. Sustained isolation degrades it. This makes serotonin respond to the *shape of her social life* over time, not individual messages.

**Baseline function change:**

```python
# In _serotonin_baseline_fn, after existing T3/estradiol/BDNF modulation:
isolation = ctx.get("isolation_pressure", 0.0)  # 0–100
# Regular social contact supports serotonin; isolation degrades it
# ±2 ng/mL swing across the full isolation range
social_factor = 1.0 + (50.0 - isolation) / 100.0 * 0.18
base *= max(0.7, min(1.18, social_factor))
```

**Ceiling adjustment:** With social encoding removed, the current hard ceiling of 55 ng/mL is too permissive. The registry label "VERY STABLE" starts at 38. Lower soft: 40 → 30, hard: 55 → 40. Even sustained exercise and good eating shouldn't push past "VERY STABLE."

---

#### Acetylcholine (from `encode_response` only)

**Problem:** ACh does respond to focused attention and cognitive engagement, so encoder involvement is not wrong in principle. However, `encode_response()` fires on every single reply and consistently posts `acetylcholine: +4–6`. The tonic level is already managed by `_ach_baseline_fn` (which suppresses it with sleep deprivation and chronic cortisol). Encoder-driven ACh from Mina's own responses is redundant and stacks on top of the baseline function, pushing ACh near its ceiling chronically.

**Fix:**
- Remove ACh from `encode_response()` entirely.
- Keep it in `encode_stimulus()` for genuinely cognitively engaging incoming content (novel ideas, problems to think through, surprising information).
- Keep it in `encode_activity()` for cognitively demanding tasks.

---

### ⚠️ Keep but tighten guidance

#### Endorphins

**Problem:** Endorphins (β-endorphin) are released by physical exertion, sustained laughter, pain, and intense physical exertion. They do not respond to "engaged energetic expression" or routine conversation. The encoder currently posts `endorphins: +8–12` for ordinary replies.

**Fix:** Tighten the encoder prompt guidance to be explicit:

> **Endorphins (pg/mL):** Physical exertion, genuine sustained laughter, warmth/touch, pain response only. Do NOT post endorphins for intellectual engagement, curiosity, or routine conversation — that is dopamine's territory. A normal reply, however warm, is not an endorphin event.

---

### ➕ Add to `_DELTA_FIELDS`

#### Anandamide

**Why missing:** Anandamide is the primary endocannabinoid responsible for the "runner's high" (endorphins cannot cross the blood-brain barrier at meaningful concentrations; anandamide can). It is also released during relaxation, creative flow states, and mild physical warmth. Exercise without anandamide is biologically incomplete.

**Scope:** Activity encoder only. Add to `_DELTA_FIELDS` and add guidance:

> **Anandamide (nM, resting ~1.5):** Exercise is the primary trigger — moderate to intense cardio: +1.5–3.5. Relaxation, warm bath, creative flow: +0.5–1.5. Not a social event chemical. Do not post for conversation.

Stored in `state.body["anandamide"]`, same as existing model. `clamp_chemical` handles bounds.

---

#### Prolactin (neuroendocrine tier)

**Why missing:** Prolactin spikes sharply post-peak and is the primary driver of the refractory period — the "satisfied, done, want to sleep" signal. The current peak-resolution `event_override` models only the dopamine crash, norepinephrine drop, and sleep pressure increase. This captures the withdrawal side but misses the active satiation signal entirely.

**Scope:** Peak-resolution `event_override` only. Add to `_DELTA_FIELDS` and add to the calibrated magnitude guidance:

> - Peak resolution: dopamine −100 to −150, sleep_pressure +30 to +40, norepinephrine −60 to −100, **prolactin +8 to +15 ng/mL** (post-peak satiation signal; promotes bonding and sleep drive)

Prolactin is stored in `state.neuroendocrine["prolactin"]`. The encoder should write to that path, not `state.chemicals`. Since `_DELTA_FIELDS` only covers `state.chemicals`, this requires either routing prolactin through `apply_deltas()` as a neuroendocrine key or adding a neuroendocrine delta path in the encoder. See open questions.

---

## Summary of Changes

| File | Change |
|---|---|
| `src/bio/encoder.py` | Remove `serotonin` from `encode_stimulus()` / `encode_response()` system prompts; keep in activity. Add `anandamide` and `prolactin` to `_DELTA_FIELDS` and event_override guidance. Remove ACh from `encode_response()` prompt. Tighten endorphin prompt guidance. |
| `src/sim/chem/registry.py` | Lower serotonin soft_ceiling 40 → 30, hard_ceiling 55 → 40. |
| `src/sim/chem/registry.py` | Add `anandamide` delta path wiring (already stored in body; confirm `clamp_chemical` covers it). |
| `src/sim/chem/registry.py` | `_serotonin_baseline_fn`: add `isolation_pressure` social factor. |
| `src/bio/state.py` / `apply_deltas()` | Support neuroendocrine delta path for prolactin (or confirm existing path handles it). |

---

## Open Questions

1. **Prolactin delta path:** The encoder currently writes deltas to `state.chemicals`. Prolactin lives in `state.neuroendocrine`. Does `apply_deltas()` support neuroendocrine keys, or do we need to add a second delta dict / routing layer? Resolve before implementing prolactin.

2. **Serotonin activity guidance magnitude:** Once social encoding is removed, what's the right range for activity-driven serotonin? Current guidance is `+1–3` for positive social. For a meal it should probably be `+2–5`; for exercise `+3–8`. Calibrate against charts after first deploy.

3. **Anandamide secretion queue:** Should anandamide go through the secretion queue (drip release) like dopamine/oxytocin, or apply immediately? Its FAAH-mediated half-life is ~15 minutes (approach_rate 2.8/hr already set), so drip is probably unnecessary — immediate application followed by fast enzymatic decay is more accurate.

4. **State wipe:** Current state has serotonin at 47.7 ng/mL (above the new hard ceiling of 40) and oxytocin at 62.7 pg/mL. A state wipe to defaults would allow clean validation of these changes immediately. Optional — natural decay would return values to range within ~24h of no interaction — but a wipe makes the fix verifiable in one session.
