# SPEC-44: Normalized Chemistry Scale for Adjudicator

**Status: DRAFT — approved for implementation**

---

## Problem

The adjudicator currently receives chemistry information through a flag system: chemicals are only surfaced when they cross a hard threshold into an "out of range" state. This means:

- A cortisol reading of 290 (quietly elevated, building unease) is invisible — the flag threshold is 520
- The adjudicator cannot read *combinations* — it sees individual flags, not the full chemical picture
- Low values are as meaningful as high ones ("low cortisol + high oxy + high endo = safety and warmth") but only high-side flags exist for most chemicals
- Drugs that push chemicals above natural maximums have no clean representational path

The result: the adjudicator is reading an incomplete picture and making emotional decisions without the full story.

---

## Solution

Replace the chemistry flags section in `_build_emotional_profile` with a **normalized 0–10 table** for all tracked chemicals, derived directly from the registry's `hard_floor` and `hard_ceiling` values.

```
normalized = (current - hard_floor) / (hard_ceiling - hard_floor) * 10
```

- **0** = physiological rock bottom (hard floor)
- **10** = human natural maximum (hard ceiling, no substances)
- **Above 10** = substance-assisted — beyond what the body produces on its own
- **Clamped at 0** minimum; no maximum cap (substances freely exceed 10)

Each chemical includes its **resting reference** inline so the adjudicator knows what "normal" looks like for that specific chemical without needing labels.

### Example output (replacing current [CHEMISTRY] flags section)

```
[CHEMISTRY — normalized 0–10, resting ref in parens]
cortisol:       4.8  (rest ~3.0)   ← above resting, something is activating
norepinephrine: 2.5  (rest ~2.5)   ← at resting
epinephrine:    2.1  (rest ~1.5)   ← slightly above resting
dopamine:       4.4  (rest ~4.5)   ← at resting
oxytocin:       0.5  (rest ~0.5)   ← no bond
serotonin:      5.5  (rest ~5.5)   ← stable
endorphins:     1.3  (rest ~1.2)   ← at resting
acetylcholine:  3.2  (rest ~3.2)   ← at resting
```

Drugs pushing above 10:
```
endorphins:    14.2  (rest ~1.2)   ← substance-assisted; beyond natural range
```

---

## Adjudicator prompt changes

The adjudicator system prompt gets a new reading-order instruction:

**Step 1 — Cortisol as the alert signal**
Read cortisol first. Is it above resting? How far? This tells you whether the body is activated. If yes, proceed to step 2. If no, the body is not in an alert state.

**Step 2 — Valence chemicals determine what kind of activation**
Read oxytocin, endorphins, dopamine together.
- Cortisol elevated + oxy/endo high → safe arousal (excitement, desire, intensity with warmth)
- Cortisol elevated + oxy/endo low → threat state (unease, suspicion, defensiveness)
- Cortisol elevated + oxy/endo mixed → ambivalent activation (conflicted, nervous-excited)

**Step 3 — Absolute zero is a value**
Low cortisol is not neutral — it is safety. The body has stood down. Low cortisol + high oxy/endo = the closest state to genuine peace the sim produces.

**Step 4 — Above 10 means substances**
Values above 10 are beyond what the body produces naturally. The adjudicator should treat these as overriding the normal emotional register — not an extreme version of normal, but a qualitatively different state.

---

## What changes

### `src/brain/subconscious/decoder.py`

1. **Remove** `_CHEM_FLAG_THRESHOLDS` and `_CHEM_FLAG_DESCRIPTIONS` dicts
2. **Add** `_normalize_chemistry(state) -> str` function that:
   - Iterates tracked chemicals from the registry
   - Computes normalized value: `(current - hard_floor) / (hard_ceiling - hard_floor) * 10`
   - Computes resting reference: `(resting_baseline - hard_floor) / (hard_ceiling - hard_floor) * 10`
   - Formats as a table with resting ref inline
   - Clamps at 0 minimum, no maximum cap
3. **Replace** chemistry flags section in `_build_emotional_profile` with `_normalize_chemistry(state)` output
4. **Update** `_ADJUDICATOR_SYSTEM_ACTIVE` and `_ADJUDICATOR_SYSTEM_FREETIME` with the combination-reading instruction above
5. **Remove** the trajectory section's dependency on `_CHEM_FLAG_THRESHOLDS` — trajectory still runs but uses the normalized values for comparison

### `src/brain/subconscious/decoder.py` — trajectory section

The trajectory section (`[CHEMISTRY TRAJECTORY]`) currently uses flag thresholds to decide what to surface. After this change, trajectory should surface any chemical that moved more than **1.0 normalized unit** since the last snapshot — coarser than the current flag system but cleaner and threshold-free.

---

## What does NOT change

- The derived emotional profile (anxiety, depression, loneliness, etc.) — stays as-is
- The biological report compact (`biological_report_compact`) used for BIO/REPORT logging — stays as-is, still uses labels
- The encoder — still fires raw pg/mL / nmol/L deltas, normalization happens only at the adjudicator boundary
- The registry — no changes needed; `hard_floor`, `hard_ceiling`, and `resting_baseline` are already present on all chemicals

---

## Chemicals included in the normalized table

From registry, all chemicals with meaningful hard_floor and hard_ceiling:
`cortisol`, `epinephrine`, `norepinephrine`, `dopamine`, `serotonin`, `oxytocin`, `endorphins`, `acetylcholine`, `gaba`, `melatonin`, `anandamide`, `glucose`, `hydration`

Substances (alcohol, MDMA, etc.) are included when active — their levels naturally exceed 10 and that is the signal.

Chemicals with `resting_baseline=0` (prolactin, glutamate) are included but their resting ref shows as 0 — the adjudicator reads them as "only present when something happened."

---

## Open questions

1. **Should epinephrine and norepinephrine be shown separately or combined?** They co-activate on SAM axis events and tell similar stories. Showing both may add noise. For now: show both, with a note that they often move together.

2. **Glucose and hydration** — these are metabolic, not mood chemicals. They have meaningful phenomenology (hypoglycemia, dehydration) but are less about emotion and more about physical state. Include them but consider whether they clutter the table.

3. **Table format** — the example above uses inline resting refs. An alternative is a two-column format (value | delta from resting). The delta format makes deviations more obvious but adds complexity. Recommendation: start with inline refs, revisit if the adjudicator isn't reading deviations well.
