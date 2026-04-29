# SPEC-59 — Dedicated `eat` and `drink` Tools

## Problem

The current `do_action` tool handles eating and drinking as generic activities. `evaluate_activity_deltas` applies flat heuristic deltas (+40–65 mg/dL glucose for any meal, 0.4% TBW hydration for any drink). This produces unrealistic outcomes:

- A tiny snack and a full breakfast give nearly the same glucose bump
- The actual hunger/satiety hormones (ghrelin, leptin) are not driven by eating events
- Hydration doesn't distinguish between water, juice, milk, coffee, alcohol, or soup
- Caffeine in drinks doesn't trigger the cortisol/alertness response it should
- The LLM has no structured way to think about what she consumed

Additionally, the glucose awake decay rate (6.5 mg/dL/hr) was identified as biologically incorrect — it's roughly 8× too fast and models heavy exercise, not a resting person. The liver compensates most glucose demand during normal fasting. This will be corrected as part of this spec.

---

## Goals

1. **Replace `do_action` eating/drinking with dedicated `eat` and `drink` tools** that take structured food/drink descriptions and compute realistic physiological effects.
2. **Drive ghrelin and leptin properly** — eating suppresses ghrelin and boosts leptin; fasting does the reverse. These should be the primary hunger signal visible to Mina.
3. **Fix glucose decay rates** to match resting physiology.
4. **Scale meal effects to actual content** — a small snack does less than a full meal; recovery from hypoglycemia requires meaningful food.
5. **Handle drink type correctly** — water, milk, juice, coffee, alcohol all have different effects.

---

## Glucose Decay Rate Fix

`src/engine/physio/metabolic.py` → `_advance_glucose`:

| State | Current | Corrected | Rationale |
|-------|---------|-----------|-----------|
| Sleeping | 0.8 mg/dL/hr | 0.3 mg/dL/hr | Hepatic output nearly matches minimal use during sleep |
| Awake/resting | 6.5 mg/dL/hr | 0.8 mg/dL/hr | Liver compensates ~90% of demand; net fall is slow |

With the corrected rate, a 12-hour overnight fast takes glucose from ~85 to ~75 mg/dL — realistic, still noticeable, but not catastrophic.

The insulin-mediated post-meal clearance term stays as-is (`decay_rate += (insulin - 40.0) * 0.08`) — this correctly models the spike-and-clear arc after eating.

---

## New Tools

### `eat` Tool

**Schema:**

```json
{
  "name": "eat",
  "description": "Eat something. Describe exactly what you eat and how much — the physiological effect scales with content. A small snack vs. a full meal vs. eating when hypoglycemic all produce different results.",
  "parameters": {
    "type": "object",
    "properties": {
      "description": {
        "type": "string",
        "description": "What you ate and roughly how much. Be specific: 'two scrambled eggs and a slice of toast' vs. 'eggs, bacon, toast, fruit, and chocolate milk'. More detail = more accurate effect."
      }
    },
    "required": ["description"]
  }
}
```

**Handler — `handle_eat(args, state) -> (str, BiologicalState)`:**

The handler calls a dedicated LLM encoder pass (similar to `evaluate_activity_deltas` but structured) that:

1. Estimates **glycemic load** from the food description (low/medium/high/very high)
2. Estimates **meal size** (snack / light / moderate / full / large)
3. Estimates **protein and fat content** (affects serotonin, satiety duration)
4. Applies deltas directly — does not queue as a pending_do

**Delta table (all values are deltas in native units):**

| Variable | Rule |
|----------|------|
| `glucose` | Base: snack +10–20, light +20–35, moderate +35–50, full +50–65, large +65–80. High glycemic index food shifts toward upper end of range. If glucose < 55 (hypoglycemic), add +10 bonus (counter-regulatory response). |
| `ghrelin` | Suppressed: snack −100–150, light −150–200, moderate −200–300, full −300–400, large −350–500 pg/mL. Resets toward baseline over the next few hours via existing `_advance_ghrelin`. |
| `leptin` | Modest boost from feeding signal: +0.5–2.0 ng/mL scaled to meal size. |
| `insulin` | Spike proportional to glycemic load: low GI +5–15 µIU/mL, high GI +20–50 µIU/mL. The metabolic loop then handles clearance. |
| `serotonin` | +2–6 ng/mL. Higher for protein-rich meals (tryptophan source). Comfort food (pasta, sweets, bread): upper end. |
| `endorphins` | +3–10 pg/mL for pleasurable comfort food; +1–3 pg/mL for plain/neutral food. |
| `cortisol` | −5–15 nmol/L if ghrelin was elevated (hunger stress relieved). Zero if not hungry. |
| `dopamine` | +3–8 ng/mL if the food was enjoyable or anticipated. |

**Tool result text** returned to Mina should acknowledge the actual food she ate, not a generic confirmation.

---

### `drink` Tool

**Schema:**

```json
{
  "name": "drink",
  "description": "Drink something. Describe what and how much — the effect depends on the drink type, volume, and any active substances.",
  "parameters": {
    "type": "object",
    "properties": {
      "description": {
        "type": "string",
        "description": "What you drank and how much. Be specific: 'a large glass of water', 'a mug of black coffee', 'a glass of chocolate milk', 'a beer'."
      }
    },
    "required": ["description"]
  }
}
```

**Handler — `handle_drink(args, state) -> (str, BiologicalState)`:**

The encoder classifies the drink along two axes: **type** and **volume**.

**Type classification and effects:**

| Type | Hydration (% TBW) | Other |
|------|-------------------|-------|
| Water | +1.0–2.5 (volume-scaled) | — |
| Milk / chocolate milk | +0.8–2.0 | glucose +5–15, serotonin +1–2, endorphins +2–5 (comfort) |
| Juice / sports drink | +0.8–1.8 | glucose +10–25 (high sugar) |
| Tea (plain) | +0.8–1.8 | mild anxiolytic (L-theanine): gaba +0.1–0.3 |
| Coffee / espresso | +0.4–0.8 (mild diuretic offset) | acetylcholine +2–5, cortisol +15–30, norepinephrine +10–20 |
| Soup / broth | +1.0–2.0 | glucose +5–10, serotonin +1–3, endorphins +2–6 (comfort) |
| Alcohol (beer/wine/spirits) | +0.3–0.6 (net after diuresis) | BAC += volume × ABV estimate; gaba +0.3–0.8; see existing alcohol path |
| Soda | +0.5–1.2 | glucose +15–30 (high sugar), caffeine if cola |

**Volume scaling:** a sip vs. a glass vs. a large bottle all scale the above. The encoder estimates volume from the description ("a sip", "a glass", "a large mug", "a bottle").

**Ghrelin:** Small suppression from drinking in general (stomach distension signal), especially for caloric drinks.

---

## Ghrelin as the Visible Hunger Signal

Currently the freetime prompt and bio profile show `energy` as the primary low-fuel indicator. Ghrelin should be surfaced explicitly:

- **`src/brain/subconscious/profile.py`** — include ghrelin in the biological profile output when elevated, with a human-readable label ("stomach growling", "strong hunger", "ravenous")
- **`src/brain/brainstem/vital_signs.py`** or a new `needs_summary` block — when ghrelin > 600 pg/mL, include a hunger urgency note in the freetime stimulus text
- The freetime prompt in `_build_freetime_suffix` should reference ghrelin level explicitly when high, not just low energy

**Ghrelin labels (for profile display):**

| Value (pg/mL) | Label |
|---------------|-------|
| < 200 | SATIATED |
| 200–400 | NORMAL |
| 400–600 | HUNGRY |
| 600–800 | STRONG HUNGER |
| > 800 | RAVENOUS |

---

## Freetime Prompt: Eating Urgency

In `_build_freetime_suffix`, when ghrelin > 600 pg/mL **or** glucose < 70 mg/dL, prepend a directive before the tool menu:

```
⚠ Your body needs food. Ghrelin is elevated — you're hungry. Eat before anything else.
```

When glucose < 55 mg/dL (hypoglycemic), make this stronger:

```
⚠ HYPOGLYCEMIC. Your blood sugar is critically low. You must eat now — this overrides everything else.
```

This replaces relying on Mina to infer physical need from abstract energy values.

---

## do_action: Remove Eating and Drinking

Once `eat` and `drink` are live, the `evaluate_activity_deltas` prompt removes the eating/drinking delta guidance and the tool description for `do_action` explicitly excludes them:

> "For eating and drinking, use the dedicated `eat` and `drink` tools instead."

`do_action` continues to handle exercise, reading, showering, creative activities, walking, etc.

---

## Implementation Plan

1. **Fix glucose decay rates** in `metabolic.py` (two-line change, no other dependencies)
2. **Write `handle_eat` and `handle_drink`** in `src/engine/physio/feeding.py` (new file) — LLM encoder call + delta application
3. **Add `eat` and `drink` to `HEARTBEAT_TOOLS`** in `tools.py`; add `call_tool` dispatch cases
4. **Update ghrelin labels** in `registry.py` and surface in `profile.py`
5. **Update `_build_freetime_suffix`** to include hunger urgency directives
6. **Update `evaluate_activity_deltas` prompt** to remove eating/drinking guidance
7. **Update `do_action` tool description** to redirect to `eat`/`drink`

---

## Tool Availability and Conversation Behavior

Eating and drinking are primarily **freetime behaviors** — Mina feeds herself autonomously when alone, not in response to user commands mid-conversation. `eat` and `drink` should remain `HEARTBEAT_TOOLS` only, consistent with `do_action`.

When a user suggests she eat during a conversation, the expected outcome is that she acknowledges it and follows through in the next freetime session — not that she calls the tool immediately mid-message. The freetime urgency directives (above) are the mechanism that ensures she actually acts on it.

**Known issue:** When Mina wants to eat during a conversation turn, she tends to narrate the tool call as emote text (`*do_action("eat...")*`) rather than invoking it as a function — likely because calling a tool mid-conversation feels like breaking the narrative. This is less critical since eating is freetime-primary, but the character instructions (MINA.md or KAG) should clarify that using `eat`/`drink` tools *is* the physical act, not a meta-operation.

## Resolved Decisions

- **Chocolate milk**: The LLM encoder handles it naturally from the description — no special routing needed.
- **Hydration from food**: `eat` contributes a small hydration delta for water-rich foods. The encoder estimates this from description: soup/broth +0.5–1.0% TBW, juicy fruit +0.2–0.4% TBW, standard solid food +0.0%.
