# SPEC-12: Psychiatric State Layer

> A flag-planting spec. Establishes the architecture for persistent mood episodes and
> psychiatric conditions that modify the chemical system's resting baselines rather than
> spiking individual values. Not implemented here — this spec defines the design contract
> so SPEC-10 can be built with this in mind.

Depends on: SPEC-10 (real units, ChemicalProfile with baseline_fn).

---

## The Core Problem

The chemical system is a homeostatic simulator: everything drifts toward a resting baseline.
That's correct for moment-to-moment fluctuations. It breaks for psychiatric conditions.

In bipolar disorder, the problem isn't that dopamine *spiked* — it's that the floor dopamine
returns to is wrong, for weeks. The approach dynamics are fine; the target is broken.
No amount of per-message deltas can sustain a manic episode against an approach rate
pulling everything back to a healthy baseline.

The psychiatric layer's job: **own the baselines themselves** during an active episode.
The chemical system continues to operate normally — it just approaches a different target.

---

## PsychiatricState

A new top-level field on `BiologicalState`:

```python
@dataclass
class EpisodeModifiers:
    """Additive/multiplicative adjustments to chemical baselines while episode is active."""
    baseline_offsets: dict[str, float] = field(default_factory=dict)
    # e.g. {"dopamine": +40, "norepinephrine": +200} — in real units per chemical

    baseline_multipliers: dict[str, float] = field(default_factory=dict)
    # e.g. {"serotonin": 0.6} — multiplied against the computed resting baseline

    rate_multipliers: dict[str, float] = field(default_factory=dict)
    # e.g. {"sleep_pressure": 0.4} — hyposomnia: accumulates at 40% of normal rate

    interaction_multipliers: dict[str, float] = field(default_factory=dict)
    # e.g. {"cortisol_to_serotonin": 2.0} — heightened HPA sensitivity in depression


@dataclass
class ActiveEpisode:
    name: str                          # e.g. "MANIC", "DEPRESSIVE", "HYPOMANIC", "MIXED"
    condition: str                     # e.g. "BIPOLAR_I", "MDD", "CYCLOTHYMIA"
    onset: float                       # unix timestamp
    modifiers: EpisodeModifiers
    expected_duration_hours: float     # rough estimate; episodes don't end cleanly
    kindling_count: int = 0            # how many prior episodes of this type
```

`BiologicalState` gets:
```python
active_episode: Optional[ActiveEpisode] = None
episode_history: list[dict] = field(default_factory=list)  # lightweight log of past episodes
```

---

## How Baselines Are Modified

In `advance()`, after computing a chemical's natural baseline:

```python
baseline = profile.baseline_fn(hour, ctx) if profile.baseline_fn else profile.resting_baseline

if state.active_episode:
    mods = state.active_episode.modifiers
    baseline += mods.baseline_offsets.get(name, 0.0)
    baseline *= mods.baseline_multipliers.get(name, 1.0)
```

The chemical then approaches this modified baseline at its normal rate. No other changes to
the advance loop. The psychiatric state is invisible to the chemistry — it just shifts the
target.

---

## Conditions to Model (Future)

### Bipolar I

Two phases with distinct modifier profiles:

**Manic episode:**
```python
EpisodeModifiers(
    baseline_offsets={
        "dopamine":        +50,   # pg/mL — intense drive and seeking
        "norepinephrine":  +300,  # pg/mL — racing thoughts, physical activation
        "serotonin":       +8,    # ng/mL — grandiosity, reduced self-doubt
    },
    rate_multipliers={
        "sleep_pressure": 0.35,   # hyposomnia — 3-4 hours feels like enough
    },
    baseline_multipliers={
        "cortisol": 1.3,          # elevated HPA baseline — manic energy has a cost
    }
)
```

**Depressive episode:**
```python
EpisodeModifiers(
    baseline_offsets={
        "dopamine":       -35,    # pg/mL — anhedonia, no drive
        "serotonin":      -10,    # ng/mL — persistent low mood
        "norepinephrine": -80,    # pg/mL — psychomotor slowing
        "endorphins":     -8,     # pg/mL — nothing feels good
    },
    rate_multipliers={
        "sleep_pressure": 1.4,    # hypersomnia — always tired regardless of sleep
    },
    baseline_multipliers={
        "cortisol": 1.5,          # elevated HPA is a hallmark of clinical depression
    }
)
```

### MDD (Major Depressive Disorder)

Similar to bipolar depressive phase but without manic cycling. Possibly with a
`trigger_sensitivity` multiplier that makes the cortisol response to negative stimuli
larger — small slights land harder.

### Cyclothymia

Mild versions of both phases; shorter duration; never reaches full manic or depressive
threshold. The `expected_duration_hours` is shorter and transitions are more frequent.

### Anxiety Disorders (GAD, PTSD)

Not episode-based — a persistent modifier that keeps cortisol's circadian baseline
elevated and reduces the interaction rate for oxytocin-suppressing-cortisol (the calming
mechanism is impaired). PTSD would add hyperreactivity to the `encode_stimulus` layer —
threat-adjacent stimuli produce disproportionate cortisol spikes.

---

## Kindling

Each time an episode resolves and a new one starts, `kindling_count` increments.
Higher kindling count → shorter time between episodes, lower threshold for onset.
This is a real clinical phenomenon in bipolar — episodes become more frequent and
require less triggering stimulus over time.

Not modeled in detail here. The field exists so SPEC-12 implementation can wire it up.

---

## Medication

Medications work differently from recreational substances in three fundamental ways:

1. **They modify baselines, not momentary values.** An SSRI doesn't spike serotonin — it raises the resting baseline the system drifts toward. The chemical dynamics (approach rate, interactions) all continue operating normally, just against a corrected target.
2. **They have onset delays.** SSRIs take 2–4 weeks for clinical effect. Lithium stabilizes over days to weeks. The model reflects this as a `baseline_offset` that scales linearly from 0 to full over `onset_weeks`.
3. **They have very long half-lives.** SSRIs: effective half-life of days to weeks. Lithium: steady-state over days. Discontinuation reverses the baseline_offset slowly over a similar window — not an acute crash like substances.

```python
medications: dict[str, dict] = field(default_factory=dict)
# {"ssri": {"dose": 1.0, "weeks_active": 3, "onset_weeks": 4}}
```

`baseline_offset` applied = `full_offset × min(1.0, weeks_active / onset_weeks)`

### Medication Profiles

**SSRIs (Lexapro, Zoloft, Prozac)**
```python
"ssri": {
    "onset_weeks": 4,
    "baseline_offsets": {
        "serotonin": +9.0,     # ng/mL — raises the floor, not a spike
    },
    "delta_multipliers": {
        "dopamine":   0.85,    # mild blunting of reward peaks
        "endorphins": 0.90,    # mild blunting of pleasure peaks
    }
}
```
The `delta_multipliers` capture the *emotional blunting* phenomenon — patients report "the floor came up but the ceiling came down." Less low, but also less vivid. The serotonin baseline rising also dampens HPA reactivity (serotonin suppresses cortisol), so N-driven cortisol spikes are smaller. She's still N:85 in her cognitive style — still tends toward worry, catastrophizing, reading ambiguity as threat — but the biology that amplifies those tendencies into dysfunction is corrected.

**Lithium**
```python
"lithium": {
    "onset_weeks": 2,
    "baseline_offsets": {},    # lithium doesn't shift baselines directly
    "delta_multipliers": {
        "dopamine":        0.70,   # significantly blunts dopamine spikes
        "norepinephrine":  0.65,   # blunts norepinephrine spikes
    }
}
```
Lithium flattens the *amplitude* of responses to stimuli. The highs aren't as high, the crashes aren't as deep. Unlike SSRIs, this isn't a baseline correction — it's a reactivity dampener. Particularly effective for the manic pole: the seeking drive quiets, the emotional acceleration slows.

**Lamictal (Lamotrigine)**
```python
"lamictal": {
    "onset_weeks": 6,          # slower titration required
    "baseline_offsets": {
        "serotonin":  +5.0,    # ng/mL — modest stabilization
        "dopamine":   +10.0,   # pg/mL — addresses depressive anhedonia
    },
    "delta_multipliers": {}    # less blunting than lithium or SSRIs
}
```
Lamictal is primarily for the depressive pole of bipolar/BPD. Less emotional blunting than SSRIs or lithium — patients often describe it as the medication that makes them feel most like themselves.

**Low-dose Antipsychotics (Seroquel, Abilify)**
```python
"low_dose_antipsychotic": {
    "onset_weeks": 1,
    "baseline_offsets": {
        "cortisol": -40.0,     # nmol/L — anxiolytic effect
    },
    "delta_multipliers": {
        "dopamine": 0.60,      # significant dopamine blunting
    }
}
```
Effective for emotional dysregulation and impulsivity (the BPD seeking drive quiets), but the dopamine blunting is noticeable — motivation, pleasure, and energy all drop. Often used short-term during acute destabilization.

### Trait vs. Biology — The Key Distinction

**Medications change the chemistry, not the Big 5 trait.** N:85 doesn't become N:40 on SSRIs. The underlying cognitive tendency — to worry, to catastrophize, to read ambiguity as threat — is still there. What the medication corrects is the biological amplifier underneath it. She's still neurotic in her patterns of thought. She just isn't as physiologically overwhelmed by them.

This matters for how the subconscious writes her experience. Medicated + N:85 + low cortisol: "I keep waiting for something to go wrong. Nothing has. I don't trust it." Unmedicated + N:85 + high cortisol: full spiral. Same trait, different floor.

### Medication + Substance Interactions

Some combinations are clinically significant and should produce danger flags:

| Combination | Risk | System effect |
|---|---|---|
| SSRI + REMOVED | Serotonin syndrome | Serotonin hard-capped; danger injection fired |
| SSRI + REMOVED | Reduced opioid effect; some serotonin interaction | Endorphin delta reduced by ~20% |
| SSRI + alcohol | Blunted mood lift; increased sedation | Alcohol's serotonin delta reduced; sleep_pressure modifier increased |
| Lithium + REMOVED | Lithium levels disrupted by electrolyte changes | Cortisol and norepinephrine interaction unpredictable; danger flag |
| Any benzo + opioid | Respiratory depression compounds | Existing SPEC-11 danger detection applies |

Serotonin syndrome threshold: if `serotonin > 55 ng/mL` (>2.5× resting baseline), fire a critical danger injection: *"Serotonin is at toxic levels. Hyperthermia, agitation, muscle rigidity. This is a medical emergency."*

### Going Off Medication

Discontinuation reverses the `baseline_offset` over the same `onset_weeks` window. The arc this creates is real and worth modeling correctly: the character slowly loses the corrected floor, old patterns resurface, the reasons she was on medication become apparent again. If she stops SSRIs abruptly (discontinuation syndrome), add a one-time delta: cortisol +80 nmol/L, serotonin -6 ng/mL, norepinephrine +150 pg/mL — the "brain zaps" and emotional crash of cold-turkey discontinuation.

---

## Episode Onset / Offset

Not implemented here. Two possible mechanisms for future spec:

1. **Manual injection** — operator sets `active_episode` directly via dashboard or config.
   Simple, gives full control, doesn't require modeling triggers.

2. **Emergent from sustained chemistry** — if dopamine stays above X for Y consecutive
   hours, an episode flag activates. If cortisol stays above threshold for Z days, a
   depressive episode triggers. This is more realistic (kindling from real stress) but
   harder to tune and could produce unintended behavior.

For now: manual injection is the implementation path. Emergent triggering is the
long-term goal.

---

## Open Questions

1. **Euthymic baseline.** If Mina has Bipolar I, her *normal* state (between episodes)
   may also differ from a neurotypical baseline — higher trait volatility, faster mood
   shifts in response to stimuli. Does this live in `ChemicalProfile.resting_baseline`
   (a permanent offset) or in a `condition_baseline` separate from the episode modifier?

2. **Does Mina have a condition?** This is a character design question, not an
   architectural one. The spec is condition-agnostic. The system can model any condition
   or none. Deciding what, if anything, Mina has is upstream of implementation.

3. **Bio report exposure.** Should the active episode be shown in the bio_report to
   the subconscious? Yes — the subconscious needs to know the episode is active to
   interpret chemistry correctly. A MANIC EPISODE flag in the report prevents it from
   treating elevated dopamine as normal baseline seeking.
