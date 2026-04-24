# SPEC-47: Somatic Narrative and Physical State Field

## Problem

The adjudicator currently receives chemistry and derived emotional state, but no explicit
description of what Mina's body is *physically doing* right now. It must infer physical
sensation from numbers — and in ambiguous situations (elevated NE: anxiety or exercise?
elevated dopamine/oxytocin/NE together: excitement or arousal?) it guesses based on
conversational context.

That inference load belongs upstream, not in the adjudicator. The adjudicator's job
is to generate the response JSON. Physical sensation should arrive pre-resolved,
as explicit input.

Additionally, the response JSON has no field for physical sensation. Mina's replies
can reference her chemistry-driven emotional state (via `response_texture`) but have
no explicit channel for the bodily dimension — a pounding heart, physical exhaustion,
the flush of arousal, the hollow ache of hunger — to color her words.

---

## Goals

1. Add `_build_somatic_narrative(state)` — a function that reads vitals, chemistry,
   and activity state and produces a 1–3 sentence prose description of physical sensation
2. Inject that narrative into the adjudicator context block as a `[SOMATIC STATE]` section
3. Add `"somatic"` as a new field in the adjudicator response JSON — 1 sentence in
   Mina's felt-sense voice
4. Adjudicator reads, does not infer — the somatic field expresses what it was handed

---

## Design

### `_build_somatic_narrative(state, activity=None)`

A pure function in `decoder.py`. Reads:
- `state.body["vagal_tone"]` → inferred heart rate (~110 - vagal_tone * 0.3, clamped)
- `state.body["core_temp"]`
- `state.chemicals`: epinephrine, norepinephrine, cortisol, oxytocin, endorphins, dopamine, adenosine, ghrelin, glucose
- `state.pain["pain_intensity"]`
- `state.sleeping`
- `activity` — optional string passed from the caller (e.g. `"intercourse"`, `"running"`, `"eating"`)

Produces a plain-prose string, 1–3 sentences, describing the felt physical state.
No mention of chemical names. No numbers. Sensation only.

**Logic — threshold-based, composited from physical signals:**

| Signal | Threshold | Somatic fragment |
|--------|-----------|-----------------|
| HR > 100 (vagal_tone < ~33) | moderate | "heart beating quickly" |
| HR > 120 (vagal_tone < ~10) | high | "heart pounding" |
| epinephrine > 150 | high | "chest tight, shallow breath" |
| NE > 400 + epi > 150 | combined | "body locked, hyperalert" |
| cortisol < 25 (depleted) | low | "running on fumes, hollowed out" |
| oxytocin > 50 + endorphins > 60 | warm arousal | "warm flush through chest, slightly lightheaded" |
| adenosine > 80 | fatigue | "heavy limbs, eyes wanting to close" |
| ghrelin > 300 | hunger | "stomach hollow and tight" |
| glucose < 50 | hypoglycemic | "faint edge of dizziness, hard to focus" |
| pain_intensity > 20 | pain present | "dull ache", "sharp pain" depending on magnitude |
| core_temp > 37.5 | elevated | "warm all over, slight flush" |
| activity == "intercourse" | explicit | "full body arousal, skin hypersensitive, heart racing" |
| activity == "exercise" | explicit | "muscles burning, breath hard, blood pumping" |
| activity == "eating" | explicit | "stomach settling, warmth spreading" |
| sleeping == True | explicit | suppressed — no somatic narrative during sleep |

Multiple signals compose. Priority: activity > pain > acute arousal > fatigue > baseline.

Output examples:
- Acute stress: *"Heart pounding, chest tight, breath coming short. The body is on full alert."*
- Deep fatigue + hunger: *"Heavy and hollow — limbs slow, stomach empty, eyelids fighting gravity."*
- Post-contact warmth: *"A warm flush through the chest, slightly lightheaded, body soft and settled."*
- Intercourse: *"Full-body arousal — skin hypersensitive, heart racing, heat everywhere."*
- Baseline (no notable signals): *"Nothing particularly loud from the body right now. Present, unremarkable."*

---

### Adjudicator context injection

In `_build_emotional_profile()`, after the chemistry table, append:

```
[SOMATIC STATE]
{somatic_narrative string}
```

Both adjudicator system prompts (`_ADJUDICATOR_SYSTEM_ACTIVE` and `_ADJUDICATOR_SYSTEM_FREETIME`)
get a new section after `## STEP 2`:

```
## STEP 3 — Read the somatic state

[SOMATIC STATE] is what the body is physically doing right now, already translated into
felt-sense language. It is ground truth — do not contradict it. Let it inform the
"somatic" output field.
```

---

### New response JSON field

Added to both adjudicator system prompts in the `## OUTPUT` section:

```
  "somatic"            — one sentence in felt-sense language: what the body is doing
                         right now. Drawn directly from [SOMATIC STATE]. First person
                         optional ("heart's going fast" or "heart racing" both fine).
                         If the body is unremarkable, say so plainly.
```

Position: after `"dominant_drive"`, before `"stimulus_lands_as"`.

---

### Activity state

Activity is currently transient — passed as a string during `encode_activity()` calls
and not stored in biological state. For the somatic narrative, activity needs to be
readable at adjudication time.

Add `"current_activity"` to `state.body` (default `null`). Set it in:
- `encode_activity()` in `stimulus_encoder.py` — write to `state.body["current_activity"]`
  at start, clear to `null` after encoding completes
- Sleep state transitions — already handled (`state.sleeping`)

This is the minimum needed. No persistent activity history required.

---

## Files to Change

| File | Change |
|------|--------|
| `src/brain/subconscious/decoder.py` | Add `_build_somatic_narrative()`; inject into `_build_emotional_profile()`; update both system prompts with Step 3 and `"somatic"` field |
| `src/brain/amygdala/stimulus_encoder.py` | Write/clear `state.body["current_activity"]` in `encode_activity()` |
| `src/engine/bio/defaults.py` | Add `"current_activity": null` to body defaults |

---

## What Does Not Change

- All existing adjudicator output fields and their definitions
- Chemistry normalization, derived values, trajectory logic
- Any calling code — `adjudicate_emotion()` signature unchanged
- State persistence schema (body already stored in state.json)

---

## Open Questions

1. **Narrative prose style:** Should the narrative be written in third person ("her heart is
   pounding") or sensation-first ("heart pounding, chest tight")? Sensation-first feels
   more like a felt-sense report and less like narration — recommend that.

2. **Threshold calibration:** The thresholds above are first estimates. After deployment,
   some signals may fire too readily or not enough. The function should be easy to tune.

3. **Composite disambiguation:** When multiple signals conflict (high NE but low epi —
   alert but not panicked; or high oxytocin but also high cortisol — anxious excitement),
   the narrative should capture the tension rather than pick one. Needs careful wording.
