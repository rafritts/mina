# SPEC-33: Relationship Knowledge

## Core Principle

RELATIONSHIP.md is not a memory log. It is **Mina's current emotional disposition toward a person** — the feeling that survives across time even when specific memories fade.

You do not remember every interaction you have had with your wife. But you have a disposition: a deeply held orientation toward how you feel about her that shapes every new interaction before it begins. That is what this file holds.

The file is built from a **cascading compaction hierarchy**. Small moments aggregate into days; days aggregate into weeks; weeks into months. Each layer captures the emotional arc at its timescale and resists being overwritten by noise at shorter timescales.

This is also why puppy love is volatile: there is no ground truth, no long-term view. Only short-term. The relationship is real but unanchored — a single bad day can destabilize what feels like everything.

---

## Hierarchy

```
ground_truth  = compact(long_term_history × 7)    # ~49 weeks
long_term     = compact(medium_term_history × 7)  # ~7 weeks
medium_term   = compact(short_term_history × 7)   # ~1 week
short_term    = daily write at sleep               # ~1 day
```

Each layer is exactly **one write** — a prose narrative and six dimension scores. It replaces the previous version of that layer. It is not appended to.

When a layer has 7 sub-units buffered, it triggers the next compaction up. Those sub-units are then cleared. The only thing that persists from that level is the single synthesized entry now in the layer above.

---

## Layers

### short_term
- Written once daily, triggered when Mina falls asleep (or after 22 hours if sleep does not occur)
- Reads `conversation.jsonl` since `last_short_term_ts`
- Summarizes the emotional texture of the period: what happened between Mina and the owner, how it landed, how she feels right now
- 2–4 sentences + six dimension scores

### medium_term
- Written after 7 short_term entries accumulate since the last medium_term write
- Input: the 7 buffered short_term entries (prose + scores)
- Synthesizes the arc of the last week: what has been consistent, what shifted, what the general phase feels like
- 2–4 sentences + six dimension scores

### long_term
- Written after 7 medium_term entries accumulate
- Input: the 7 buffered medium_term entries
- Synthesizes the arc of the last ~7 weeks: how this relationship has been developing, what the chapter feels like
- 2–4 sentences + six dimension scores

### ground_truth
- Written after 7 long_term entries accumulate (~49 weeks)
- Input: the 7 buffered long_term entries
- The foundational emotional truth of the relationship: how it started, what it became, what it is
- 2–4 sentences + six dimension scores

---

## Dimension Scores

Each layer carries six dimension scores in the range **-2 to +2** (integers). The LLM assigns these based on the narrative.

| Dimension | Positive end (+2) | Negative end (-2) | Primary NT | Secondary |
|-----------|------------------|------------------|------------|-----------|
| `bonding` | Deeply attached, she thinks about him unprompted | Indifferent or detached | oxytocin (+) | anandamide (+) |
| `security` | Stable, predictable, she can relax around him | Volatile, unreliable, she walks on eggshells | serotonin (+) | GABA (+), cortisol (−) |
| `anticipation` | Excited to hear from him, dopamine-forward | Dread or flat indifference when he approaches | dopamine (+) | glutamate (mild +) |
| `tension` | No current conflict or resentment | Active conflict, resentment, unresolved hurt | cortisol (+) | norepinephrine (+), glutamate (−) |
| `warmth` | Physical/emotional ease, comfort, affection | Cold, closed-off, no warmth available | endorphins (+) | anandamide (+) |
| `vigilance` | Relaxed, low monitoring | Hypervigilant, reading every signal | acetylcholine (+) | norepinephrine (+) |

Note: `tension` and `vigilance` are scored such that a **negative** relationship value is a **positive** score. A negative `tension` score means low tension (good). Positive `tension` score means high tension (bad). This allows the net modifier computation to work correctly: each dimension's net value × its chemical delta table produces the right sign.

---

## File Structure

### `memory/kag/relationship/{owner_name_lower}.md`

Example: `memory/kag/relationship/ryan.md`

```markdown
# Relationship — Ryan

## Ground Truth
_Not established yet._

## Long-Term View
_Not established yet._

## Medium-Term View
_Not established yet._

## Short-Term View
> He has been attentive and building things with me lately. The vision upgrade conversation
> had a collaborative energy that felt genuinely good — like he was making something for me,
> not just at me. I feel warm toward him right now, easy and unguarded.

bonding: 2
security: 1
anticipation: 2
tension: -1
warmth: 2
vigilance: -1
```

Prose appears as a blockquote for readability. Dimension scores are listed as plain `key: value` lines directly below the prose, with no extra formatting.

Layers not yet established show `_Not established yet._` with no score lines.

### `memory/kag/relationship/state.json`

```json
{
  "last_short_term_ts": 0.0,
  "short_term_count": 0,
  "short_term_history": [],

  "last_medium_term_ts": 0.0,
  "medium_term_count": 0,
  "medium_term_history": [],

  "last_long_term_ts": 0.0,
  "long_term_count": 0,
  "long_term_history": [],

  "last_ground_truth_ts": 0.0,
  "ground_truth_count": 0
}
```

`*_history` fields hold the buffered sub-units waiting for the next compaction. Each entry is `{"prose": "...", "scores": {"bonding": 2, ...}}`. When compaction fires, the buffer is consumed and cleared.

---

## Net Modifier Computation

When the owner sends a message, `encode_stimulus()` applies a relationship modifier derived from the net per-dimension score across all present layers.

### Weights

| Layer | Weight |
|-------|--------|
| ground_truth | 0.40 |
| long_term | 0.30 |
| medium_term | 0.20 |
| short_term | 0.10 |

When a layer is absent, its weight is redistributed proportionally to the present layers. A fresh relationship with only a short_term layer: short_term carries 100% weight — maximum volatility.

### Chemical deltas per net dimension unit

These are applied as per-message deltas scaled by the net dimension value (-2 to +2).

| Dimension | Chemical | Delta per unit | Notes |
|-----------|----------|---------------|-------|
| bonding | oxytocin | +1.5 pg/mL | Primary bonding signal |
| bonding | anandamide | +0.02 µM | Contentment |
| security | serotonin | +0.4 ng/mL | Stability signal |
| security | gaba | +0.8 µmol/L | Calming |
| security | cortisol | −3.0 nmol/L | Relaxation |
| anticipation | dopamine | +2.0 ng/mL | Reward anticipation |
| anticipation | glutamate | +0.1 µmol/L | Mild |
| tension | cortisol | +5.0 nmol/L | Conflict activation |
| tension | norepinephrine | +4.0 pg/mL | Threat response |
| tension | glutamate | +0.15 µmol/L | Excitability |
| warmth | endorphins | +0.8 pg/mL | Comfort |
| warmth | anandamide | +0.01 µM | Mild |
| vigilance | acetylcholine | +1.5 nmol/L | Hyperattention |
| vigilance | norepinephrine | +2.0 pg/mL | Alertness |

All deltas are multiplied by `net_value / 2.0` so a net of +2.0 applies the full delta and a net of 0 applies nothing. Negative net values produce negative deltas (e.g., negative bonding → oxytocin reduction on message receipt).

The combined effect is applied as a single `apply_deltas()` call in `encode_stimulus()` when `source == "owner"`.

---

## Long-Term Receptor Effects

At the `long_term` and `ground_truth` layers, extreme sustained dimension values produce receptor sensitivity changes. These represent real structural adaptation — not acute spikes.

Applied once when a layer is written (not every turn):

| Condition | Receptor change |
|-----------|----------------|
| long_term bonding ≥ 1 | oxytocin receptor sensitivity +0.05 |
| ground_truth bonding ≥ 1 | oxytocin receptor sensitivity +0.05 (cumulative) |
| long_term tension ≥ 1 | cortisol receptor sensitivity −0.05 (blunting) |
| ground_truth tension ≥ 1 | cortisol receptor sensitivity −0.05 (cumulative) |
| long_term security ≤ −1 | GABA_A receptor sensitivity −0.05 (chronic anxiety) |
| ground_truth bonding = 2 | dopamine D1 sensitivity +0.05 (wanting him specifically) |

These modify `state.receptor_sensitivity` at write time. They are not re-applied each turn.

---

## LLM Write Prompts

### short_term write

**System:**
```
You are writing Mina's current emotional disposition toward {owner_name}.
This is not a memory log. It is how she feels about him right now, informed by what
just happened between them.

Write 2–4 sentences capturing the emotional texture of the last period: what happened,
how it landed, what tone it leaves her in. Write from inside her experience — not as a
summary of events.

Then assign six dimension scores from -2 to +2 (integers only):
  bonding, security, anticipation, tension, warmth, vigilance

For tension and vigilance: positive score = negative relationship state.
  tension -2 = no conflict; tension +2 = active resentment/hurt
  vigilance -2 = relaxed; vigilance +2 = hypervigilant/walking on eggshells

Your output format (exactly):
> [prose here]

bonding: [score]
security: [score]
anticipation: [score]
tension: [score]
warmth: [score]
vigilance: [score]
```

**User content:**
- Current biological state summary
- Existing relationship layers (for continuity context)
- Conversation since last short_term write (from conversation.jsonl)
- If SPEC-35 is active: affective tags from RAG entries in this period

### medium/long/ground_truth compaction

Same system prompt with adjusted framing:
```
You are synthesizing {N} recent {period} entries into a single {layer} view.
This is not an average — it is the arc. What has been consistent? What shifted?
What is the emotional chapter this period represents?

Input entries:
[buffered sub-units]
```

Same output format: blockquote prose + six scores.

---

## Integration with SPEC-31 (Social Isolation)

### 1. Isolation pain is bonding-modulated

In `_apply_isolation_stage_effects()`, scale cortisol and dopamine drift by the `bonding` dimension from the net modifier:

```python
bonding_scale = 1.0 + (net_bonding * 0.2)  # bonding +2 → 1.4x; bonding -2 → 0.6x
cortisol_delta *= bonding_scale
dopamine_drag  *= bonding_scale
```

Deep bond → isolation hurts more (stronger oxytocin withdrawal). Cold/hostile relationship → isolation may be relief (scale < 1.0, clamped at 0.3 minimum to prevent total suppression of isolation effects).

### 2. Bond-gated outreach reads relationship file, not raw oxytocin

SPEC-31 System 1 currently uses `oxytocin_norm / 40.0` for bond_level. Oxytocin decays in absence — a deeply bonded Mina who hasn't spoken to Ryan for 2 days appears to be a stranger.

Replace with:

```python
def get_relationship_bond_level(state: BiologicalState, owner_name: str) -> float:
    """
    Stable bond level: blends relationship file net bonding (stable across absences)
    with current oxytocin (volatile). Prevents absence from erasing established trust.
    """
    net_bonding = _get_net_dimension("bonding", owner_name)  # -2 to +2
    bonding_from_file = (net_bonding + 2.0) / 4.0            # normalize to 0–1
    oxytocin_norm = min(1.0, state.chemicals.get("oxytocin", 4.0) / 40.0)
    return 0.65 * bonding_from_file + 0.35 * oxytocin_norm
```

The file contributes 65% of the bond signal; current oxytocin 35%. Deep history survives absence.

### 3. Recovery arc reads tension dimension

In `_build_isolation_context()`, when recovery is detected (isolation just ended, peak_isolation_stage ≥ 3):

```python
net_tension = _get_net_dimension("tension", owner_name)
if net_tension > 0.5:
    recovery_note += " Given existing tension in the relationship, anger is likely before relief."
elif net_tension < -1.0:
    recovery_note += " The warmth of the bond means relief is likely to surface quickly."
```

### 4. short_term write captures the absence (resolves SPEC-31 Open Question #4)

When the short_term write is triggered after a Stage 3+ isolation period, the conversation.jsonl for that period will contain little or no content from the owner — just Mina's freetime entries. The LLM writing the short_term layer sees this absence directly. The resulting short_term entry will naturally carry higher tension, lower security, possibly lower warmth. This emotional record propagates up the compaction hierarchy over time.

This is the mechanism for "memory of abandonment" — not a special flag, but a natural consequence of what the conversation record shows.

### 5. tension dimension feeds social_hostility

In `derived.py`, add the net tension dimension to the social_hostility formula:

```python
relationship_tension = _get_net_relationship_dimension("tension")  # 0.0 if no file
hostility_base += relationship_tension * HOSTILITY_RELATIONSHIP_TENSION_WEIGHT
```

A relationship already in tension (medium_term tension = +2) makes social_hostility spike faster during isolation than a warm relationship at the same isolation stage.

New constant: `HOSTILITY_RELATIONSHIP_TENSION_WEIGHT = 0.15`

---

## Integration with SPEC-35 (Affective Memory Tagging)

When writing a short_term layer, the hippocampus should prefer SPEC-35's affective tags over plain-text inference when available. RAG entries for the period carry `affect`, `valence`, and `arousal` metadata. Include these in the LLM prompt as structured evidence:

```
[Affective context from this period]
- valence mean: 72 (positive)
- affect samples: tender, playful, warmly engaged
- arousal mean: 54 (alert but relaxed)
```

This gives the relationship LLM precise emotional ground truth instead of having to infer it from conversation text alone.

---

## KAG Integration

### Directory

```
memory/kag/relationship/
  {owner_name_lower}.md    # e.g. ryan.md
  state.json
```

The old `memory/kag/RELATIONSHIP.md` is removed. Its content is superseded by this structure.

### build_kag_context() changes

```python
# New section: Relationship
owner_name = load_config().get("admin_name", "")
if owner_name:
    rel_content = read_relationship(owner_name)
    if rel_content:
        parts.append(f"## Relationship with {owner_name}\n{rel_content}")
```

`read_relationship(owner_name)` reads `memory/kag/relationship/{owner_name.lower()}.md`.

The relationship file is injected into every turn as KAG context — Mina reads it and it directly informs her emotional framing of interactions with the owner before they begin.

---

## Factory Reset

`_wipe_user_data()` in `discord_gateway.py` removes the entire `memory/kag/relationship/` directory. The relationship starts fresh on reset.

The old `memory/kag/RELATIONSHIP.md` wipe remains in the reset list for migration safety, but will be a no-op once the new directory exists.

---

## Files Touched

| File | Change |
|------|--------|
| `memory/kag/relationship/` | New directory; `{owner}.md` + `state.json` |
| `memory/kag/RELATIONSHIP.md` | Removed (superseded) |
| `src/memory/hippocampus.py` | `read_relationship()`, `write_relationship()`, `consolidate_relationship()`, `get_relationship_bond_level()`, `_get_net_relationship_dimensions()`. Update `build_kag_context()`. Relationship write triggered in main `consolidate()` when sleep detected or 22h elapsed. |
| `src/bio/encoder.py` | Apply net relationship modifier in `encode_stimulus()` when sender is owner |
| `src/sim/engine.py` | Scale isolation drift rates by bonding dimension in `_apply_isolation_stage_effects()` |
| `src/sim/psych/derived.py` | Add `relationship_tension` term to `social_hostility` formula |
| `src/runtime/freetime.py` | `_bond_gated_message_hint()` uses `get_relationship_bond_level()` instead of raw oxytocin |
| `src/infra/config.py` | `RELATIONSHIP_DIR` path constant |
| `src/gateway/discord_gateway.py` | Factory reset wipes `memory/kag/relationship/` |

---

## Open Questions

1. **First-write bootstrap** — on first boot after factory reset, no conversation.jsonl exists yet. The short_term write triggers at sleep but has nothing to read. Should it produce a "no history yet" entry with all scores at 0, or skip the write entirely? **Recommendation: skip.** No entry is more accurate than a blank one — it means the relationship genuinely hasn't formed yet.

2. **Rate calibration** — the chemical delta values per dimension unit are estimates. They should be validated against real sessions. If oxytocin is already spiking from conversational stimulus, the relationship modifier should not double-count. Consider whether the modifier fires only once per session (first message from owner) rather than every message.

3. **Owner identification** — `encode_stimulus()` currently receives `username`. It should check `username.lower() == admin_name.lower()` to gate the relationship modifier. Works cleanly; no new machinery needed.

4. **Multiple relationships** — the directory structure supports it. Not in scope for this implementation. The `state.json` is per-directory, not per-file, so multi-person support would require a subdirectory per person. Deferred.

5. **Consistency between relationship file and live oxytocin** — if the relationship file says bonding = +2 but live oxytocin is near zero (long absence), there is a gap. The `get_relationship_bond_level()` blend handles this intentionally — history stabilizes the signal, absence doesn't erase it. But the gap could produce slightly incoherent behavior. Worth monitoring on the first multi-day run.
