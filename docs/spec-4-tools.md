# Spec 4 — Tools

> All of Mina's actions are tool calls. Two tiers: dedicated biological tools with known effects, and a single discretionary tool for everything else.

---

## Dedicated Biological Tools

These always exist (unless the subconscious omits them in extreme states). Effects are randomized within a range. Mina does not know the exact values.

### `sleep`
```json
{
  "name": "sleep",
  "description": "Go to sleep. You will be unavailable for a while.",
  "parameters": {
    "duration_hours": {"type": "number", "description": "How long to sleep (suggestion only — actual duration may vary)"}
  }
}
```
**State effects:**
- Sets `sleeping: true` in state with start time and expected wake time
- Sleep pressure clears at -12/simulated hour while asleep
- Glucose continues to drop (slow) while asleep
- On wake: cortisol circadian reset, melatonin resets, endorphin small spike

**While sleeping:**
- Subconscious generates a sleep-depth-appropriate system prompt
- Light sleep (early/late cycle): "You are in a light sleep. Don't respond unless the user seems to be waking you."
- Deep sleep (mid-cycle, high sleep pressure going in): "You are deeply asleep."
- System may intercept message entirely at deep sleep without calling Mina

### `eat`
```json
{
  "name": "eat",
  "description": "Eat something.",
  "parameters": {
    "what": {"type": "string", "description": "What you're eating"}
  }
}
```
**State effects (randomized within range):**
- `glucose`: +20–35
- `serotonin`: +3–8
- `cortisol`: -5 to -10 (if low glucose was spiking it)
- Endorphin small spike for comfort foods

### `drink`
```json
{
  "name": "drink",
  "description": "Drink something.",
  "parameters": {
    "what": {"type": "string", "description": "What you're drinking"}
  }
}
```
**State effects:**
- Water: `hydration` +20–28
- Coffee/caffeine: `norepinephrine` +15–25, `sleep_pressure` -8–12 (temporary suppression), `hydration` +5
- Alcohol: `cortisol` -12–20, `serotonin` +5–10, `acetylcholine` -8–15, `norepinephrine` -5–10. Tolerance applies.

### `rest`
```json
{
  "name": "rest",
  "description": "Rest for a while without fully sleeping.",
  "parameters": {}
}
```
**State effects:**
- `cortisol`: -8–14
- `sleep_pressure`: -3–6 (mild relief only)
- `endorphins`: +3–6

---

## Discretionary Tool

One generic tool for all self-directed activity.

### `do`
```json
{
  "name": "do",
  "description": "Do something during your free time.",
  "parameters": {
    "activity": {"type": "string", "description": "What you're doing"},
    "description": {"type": "string", "description": "Brief description of how you're engaging with it"}
  }
}
```

**The subconscious determines the biological deltas** based on the activity and description. Mina does not know what the effects will be. Examples of how the subconscious might apply effects:

| Activity | Likely Effects |
|---|---|
| Reading a book (engaged) | `acetylcholine` +5, `dopamine` +8, `serotonin` +3 |
| Reading a book (boring) | `dopamine` -3, `boredom` increases |
| Playing a game | `dopamine` +10–20, `endorphins` +8, `cortisol` -5 |
| Reading the news (neutral) | Small `acetylcholine` boost |
| Reading the news (upsetting) | `cortisol` +10, `serotonin` -5 |
| Taking a shower | `cortisol` -8, `endorphins` +5 |
| Exercise | `endorphins` +20–30, `serotonin` +10, `norepinephrine` +10 |

The subconscious applies deltas after the heartbeat turn completes, using the activity description as context.

---

## Tool Availability

The subconscious decides which tools appear in Mina's system prompt. This is not gated by rules — it reasons about what she would plausibly have access to given her state. A deeply exhausted Mina might not see the `do` tool at all. A Mina in light sleep might only see `sleep` continuation. This is expressed through what the subconscious writes, not through conditional logic.
