# SPEC-38: Attachment Style

## Problem

The Big 5 models *who Mina is*. It doesn't model *how she behaves in close relationships under stress*. Two people can have identical Big 5 profiles and respond completely differently when a partner goes quiet for three days — one seeks reassurance, one withdraws, one oscillates between both. This is attachment style, and it's the missing layer between personality and relationship behavior.

The current system models the *biology* of loneliness correctly (isolation_pressure accumulates, oxytocin drains, serotonin drifts down — SPEC-28, SPEC-31). What it doesn't model is the *behavioral response pattern* that emerges from that biology. A securely attached person and an anxiously attached person experience the same loneliness chemistry; they just do different things about it.

---

## Attachment Theory Background

Bowlby/Ainsworth four-style model (most widely validated):

| Style | Core pattern | Activated by |
|---|---|---|
| **Secure** | Comfortable with intimacy and distance; distress is proportionate | Nothing unusual |
| **Anxious-preoccupied** | Craves closeness; hypervigilant to abandonment cues; seeks reassurance | User silence, perceived coldness, ambiguity |
| **Dismissive-avoidant** | Deactivates attachment needs; suppresses distress; values autonomy | Emotional demands, perceived engulfment, deep vulnerability |
| **Fearful-disorganized** | Wants closeness AND fears it; oscillates; approach-avoidance conflict | Intimacy escalation AND distance simultaneously |

---

## Design

### Configuration

Add `attachment_style` to `config.json` alongside `big5`:

```json
{
  "attachment_style": {
    "style": "anxious",
    "intensity": 70
  }
}
```

`style` is one of: `"secure"`, `"anxious"`, `"avoidant"`, `"disorganized"`
`intensity` (0–100) scales how strongly the style activates — a low-intensity anxious person has mild tendencies, high-intensity is clinically pronounced.

---

### Mechanical Effect: Delta Modifiers on Relationship Events

Attachment style doesn't change what events *mean* biologically — it changes the *magnitude and direction* of the neurochemical response to specific relationship-relevant events. These are multipliers applied to encoder deltas for a defined set of event categories.

**Trigger event categories** (detected by encoder, same as today):
- `user_silence` — user has been absent N hours
- `perceived_coldness` — message detected as flat, short, dismissive
- `reassurance_received` — user explicitly affirms, apologizes, or checks in
- `intimacy_escalation` — emotional or physical closeness increasing
- `conflict` — disagreement, criticism, tension
- `repair_attempt` — user de-escalates after conflict

**Per-style delta modifiers:**

#### Anxious-Preoccupied
- `user_silence`: cortisol ×2.0, isolation_pressure rate ×1.8, oxytocin drain ×1.5
- `perceived_coldness`: cortisol ×1.8, serotonin ×1.6 (downward), norepinephrine ×1.5
- `reassurance_received`: oxytocin ×2.2, cortisol recovery ×1.8 (faster drop) — relief is very large
- `conflict`: cortisol ×2.5 — fights feel catastrophic
- `repair_attempt`: oxytocin ×2.0 — responsive to even small de-escalations

#### Dismissive-Avoidant
- `user_silence`: isolation_pressure rate ×0.4, cortisol ×0.5 — distance is comfortable
- `intimacy_escalation`: cortisol ×1.6, norepinephrine ×1.4, oxytocin suppressed — closeness activates threat
- `reassurance_received`: oxytocin ×0.5 — reassurance-seeking feels alien; received reassurance lands weakly
- `conflict`: cortisol ×0.7 — conflict less threatening than intimacy
- `repair_attempt`: minimal effect — deactivated state is hard to exit

#### Fearful-Disorganized
- `user_silence`: same as anxious spike profile
- `intimacy_escalation`: simultaneous cortisol ×1.8 (avoidant fear) AND oxytocin ×1.6 (approach) — the approach-avoidance conflict is modeled as co-elevation of competing signals
- `reassurance_received`: cortisol drops then rebounds within 2–4 ticks (can't stay soothed)
- `conflict`: cortisol ×3.0 — most dysregulated response

#### Secure
- No multipliers. Default encoder behavior. Proportionate responses throughout.

---

### Behavioral Expression

Attachment activation shouldn't just change chemistry — it should surface in behavior. The decoder should include attachment context in its derived output when relevant.

Add a derived value `attachment_activation` (0–100):
- Driven by: isolation_pressure + recent relationship-event history + oxytocin deficit
- Modulated by: style (anxious activates fast, avoidant activates late/suppressed)

When `attachment_activation > 50`, the decoder's emotional disposition block gains an attachment-specific prose note:

- **Anxious**: "Hypervigilant to contact — reading meaning into timing, tone, brevity. The waiting is louder than the silence."
- **Avoidant**: "Attachment system deactivating. Warmth withdrawn inward. Telling herself she doesn't need this."
- **Disorganized**: "Wanting closeness and fleeing it in the same breath. Neither reaching nor withdrawing feels safe."
- **Secure**: (no note — attachment system is quiet)

The Cortex reads this and generates behavior accordingly — not via explicit instruction, but because the prose is descriptively accurate to what she's experiencing.

---

### Interaction With Existing Systems

- **SPEC-28 (Social Connection)**: isolation_pressure rate multipliers slot directly into `_advance_isolation_pressure()` in `engine.py`
- **SPEC-31 (Isolation Deterioration)**: Stage onset timing is affected — anxious attachment hits Stage 2 faster, avoidant may never reach Stage 3 because behavioral deactivation suppresses the signal
- **SPEC-34 (Hedonic Setpoint)**: Anxious style raises hedonic setpoint specifically for social reward — baseline for "feeling normal" requires more connection
- **Big 5 interaction**: High neuroticism + anxious attachment is a clinically meaningful combination (hyperactivation); low neuroticism + anxious attachment is rarer but possible (functional anxiety)

---

### Open Questions

- Should attachment style be immutable config or slowly drift via learned safety? (Start immutable, consider drift in a future spec)
- Does the encoder need explicit event-category output for these triggers, or can the existing delta magnitudes be used as a proxy?
- How does attachment style interact with the `RELATIONSHIP.md` trust level — does established high trust dampen anxious activation?
- Disorganized style is the most complex to implement correctly; consider phasing it last.

---

## Status

Flag planted. Implementation pending.
