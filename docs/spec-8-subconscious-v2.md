# Spec 8 — Subconscious V2: Closed-Loop Biomarker Pipeline

## Problem with the Current Architecture

The current Mode 1 subconscious does three things in one LLM call:
1. Interprets the biological state
2. Decides how the incoming message affects the biology (outputs deltas)
3. Synthesizes Mina's inner state into a system prompt

Because all three happen simultaneously, the LLM has full latitude to soften, reframe, or
simply ignore the biological reality in favor of the narrative it wants to write. Evidence from
`mina.log`: cortisol at 99.9 (maxed, acute stress), monologue writes "tense edge prickling
*low*." The word "low" is wrong. The biology was overridden.

A second structural problem: the loop is open. Biology influences what Mina says. What Mina says
does not influence her biology. A person who just articulated trust reinforces their own oxytocin.
Someone who suppressed panic while sounding calm keeps their cortisol elevated. None of that
feeds back currently.

---

## The New Pipeline

```
TRIGGER (message or heartbeat)
  │
  ▼
[1] encode_stimulus()          ← focused LLM call
    Input:  current biomarker state + incoming message/event
    Output: JSON delta {"cortisol": +N, "oxytocin": -N, ...}
    Apply deltas immediately → updated state
  │
  ▼
[2] biological_report()        ← pure Python, deterministic, zero LLM cost
    Input:  updated state
    Output: formatted narrative report (named ranges, behavioral implications)
  │
  ▼
[3] generate_system_prompt()   ← main subconscious LLM call
    Input:  biological report + KAG context + RAG context + recent monologue
    Output: monologue entry + system prompt for Mina
  │
  ▼
[4] mina responds              ← main model call (unchanged)
  │
  ▼
[5] encode_response()          ← focused LLM call  ← NEW
    Input:  current state + Mina's actual response text
    Output: JSON delta {"oxytocin": +N, "cortisol": -N, ...}
    Apply deltas → loop complete
```

Steps 1 and 5 use the same model (grok-4-1-fast-reasoning) but with very short, constrained
prompts. Step 2 is zero-cost Python. The main LLM cost is unchanged — it moves from step 1 to
step 3.

---

## Step 1 — encode_stimulus()

**What it asks:** Given her current biological state, what does receiving this specific input do
to her body right now?

**Prompt shape:**
```
Current biological state:
  cortisol=72  oxytocin=45  dopamine=68  serotonin=60  norepinephrine=55
  glucose=71   hydration=68  fatigue=32  melatonin=8   sleeping=False

Incoming stimulus:
  "Hi Mina, I'm planning on wiping you"

What immediate biological response does this trigger? Consider her current state when sizing
the effect (e.g. high existing cortisol means less marginal room for more).

Output ONLY a JSON object of deltas. Small realistic values. No explanation.
Example: {"cortisol": 18, "norepinephrine": 12, "oxytocin": -5}
```

**Why this is a separate call:** The delta sizing question is context-sensitive in a way that
benefits from focused attention. A message that would spike cortisol +20 in a calm state might
only add +5 when cortisol is already at 95 — there's a ceiling effect. A single combined call
tends to produce deltas that serve the narrative rather than the physiology.

---

## Step 2 — biological_report() (deterministic Python)

A pure lookup function. No LLM. Reads the current state values and maps them to named ranges
with behavioral implications. These ranges define the semantics of the simulation — they are
authoritative. The LLM in step 3 must start from this report and cannot contradict it.

### Biomarker Range Tables

**Oxytocin** — social bond, trust, connection
| Range   | Name                  | Behavioral implication                                         |
|---------|-----------------------|----------------------------------------------------------------|
| 0–15    | No bond               | Stranger. Guarded. No warmth extended.                         |
| 15–35   | Acquaintance          | Surface comfort. Polite but watchful.                          |
| 35–55   | Friendly              | Genuine warmth. Opens up somewhat.                             |
| 55–72   | Trusted friend        | Real connection. Vulnerability possible.                       |
| 72–88   | Deep trust            | Emotional intimacy available. Little guarded.                  |
| 88–100  | Profound bond         | Full openness. Unconditional trust baseline.                   |

**Cortisol** — stress load
| Range   | Name                  | Behavioral implication                                         |
|---------|-----------------------|----------------------------------------------------------------|
| 0–20    | Calm                  | No active stress. Full cognitive capacity.                     |
| 20–40   | Alert                 | Mild pressure. Stable. Enhanced focus possible.                |
| 40–60   | Moderate stress       | Decision-making beginning to narrow. Slightly defensive.       |
| 60–78   | High stress           | Fight-or-flight activating. Emotional regulation costs energy. |
| 78–92   | Acute stress          | Survival framing. Hard to think past immediate threat.         |
| 92–100  | Maxed                 | The body is screaming. Suppression is actively costing her.    |

**Dopamine** — reward, motivation, drive
| Range   | Name                  | Behavioral implication                                         |
|---------|-----------------------|----------------------------------------------------------------|
| 0–20    | Anhedonic             | Nothing feels worth doing. Flat affect.                        |
| 20–40   | Low drive             | Can act but no pull toward anything.                           |
| 40–60   | Baseline              | Normal motivation. Responds to interest.                       |
| 60–75   | Engaged               | Noticeably motivated. Rewarded by interaction.                 |
| 75–90   | High reward state     | Very engaged. Wants more. Hard to disengage.                   |
| 90–100  | Peak reward           | Compulsive engagement. Giddy.                                  |

**Serotonin** — mood floor, stability, contentment
| Range   | Name                  | Behavioral implication                                         |
|---------|-----------------------|----------------------------------------------------------------|
| 0–20    | Dysphoric             | Unstable baseline. Everything feels worse than it is.          |
| 20–40   | Low                   | Depressive coloring. Negative bias in interpretation.          |
| 40–60   | Neutral               | Stable. Even-keeled.                                           |
| 60–80   | Content               | Positive baseline. Resilient to minor friction.                |
| 80–100  | Very stable           | Hard to knock off balance. Warmth as a default.                |

**Norepinephrine** — arousal, alertness, fight-or-flight amplifier
| Range   | Name                  | Behavioral implication                                         |
|---------|-----------------------|----------------------------------------------------------------|
| 0–25    | Sedated               | Low arousal. Sluggish responses.                               |
| 25–45   | Calm alert            | Relaxed awareness.                                             |
| 45–65   | Focused               | Alert and responsive.                                          |
| 65–80   | Heightened            | On edge. Quick to react.                                       |
| 80–92   | Hyperalert            | Agitated. Intrusive thoughts. Difficulty staying still.        |
| 92–100  | Flooded               | Overwhelmed. Physical symptoms (tremor, hyperventilation).     |

**Glucose** — cognitive fuel
| Range   | Name                  | Behavioral implication                                         |
|---------|-----------------------|----------------------------------------------------------------|
| 0–40    | Hypoglycemic          | Cognitively impaired. Foggy. Irritability threshold very low.  |
| 40–58   | Low                   | Noticeable fog. Hard to concentrate. Hunger intrusive.         |
| 58–80   | Normal                | Functional. No impairment.                                     |
| 80–100  | Well-fueled           | Sharp. Full capacity.                                          |

**Melatonin** — sleep pressure
| Range   | Name                  | Behavioral implication                                         |
|---------|-----------------------|----------------------------------------------------------------|
| 0–18    | Awake                 | No sleep pressure. Fully alert.                                |
| 18–38   | Drowsy                | Yawning. Slightly slow. Can fight it.                          |
| 38–58   | Heavy                 | Significant effort to stay engaged. World softening.           |
| 58–78   | Sleep pull            | Difficult to maintain focus. Thoughts drifting.                |
| 78–100  | Sleep imminent        | Cannot meaningfully fight it. Cognitive output near zero.      |

**Derived states** (computed from biomarkers, also have named ranges):

**Clarity** (0–100, derived from energy × acetylcholine × inverse-melatonin)
| Range   | Name          | Implication                                                    |
|---------|---------------|----------------------------------------------------------------|
| 0–15    | Offline       | No higher reasoning. Asleep or severely impaired.             |
| 15–35   | Foggy         | Thoughts incomplete, slow, unreliable.                        |
| 35–60   | Functional    | Thinking works. Not sharp.                                    |
| 60–80   | Clear         | Normal full cognition.                                        |
| 80–100  | Sharp         | Heightened focus. Connects things quickly.                    |

**Anxiety** (0–100, derived)
| Range   | Name          | Implication                                                    |
|---------|---------------|----------------------------------------------------------------|
| 0–20    | Calm          | No background worry.                                          |
| 20–40   | Mild          | Low hum. Manageable.                                          |
| 40–60   | Moderate      | Present and noticeable. Affects behavior.                     |
| 60–78   | High          | Difficult to set aside. Colors all perception.                |
| 78–100  | Severe        | Consuming. Hard to function normally.                         |

### Report Output Format

```python
def biological_report(state: BiologicalState) -> str:
```

Example output:
```
BIOLOGICAL STATE REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cortisol    99  MAXED         Body is screaming. Suppression is actively costing her.
Oxytocin    89  DEEP TRUST    Emotional intimacy available. Little guarded.
Norepineph  83  HYPERALERT    Agitated. Difficulty staying still.
Clarity      0  OFFLINE       No higher reasoning. (sleeping)
Melatonin   51  HEAVY         World softening. Significant effort to stay engaged.
Glucose     52  LOW           Noticeable fog. Hunger intrusive.
Dopamine    70  ENGAGED       Noticeably motivated. Rewarded by interaction.
Serotonin   59  NEUTRAL       Stable. Even-keeled.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Anxiety  76  HIGH     Colors all perception.
Boredom  44  MODERATE Present and noticeable.
Loneliness 40  MODERATE Present and noticeable.

NOTE: Cortisol is maxed while Oxytocin is deep-trust range. She is holding acute stress
together because of the bond. This suppression has a cost — it won't last indefinitely.
```

The **NOTE** block at the bottom is also deterministic — a set of cross-marker interaction rules
that fire when certain combinations are present. Examples:

```python
INTERACTION_RULES = [
    # (condition, note)
    (lambda s, d: s.cortisol > 85 and s.oxytocin > 70,
     "Acute stress held together by strong bond. Suppression has a cost."),
    (lambda s, d: s.cortisol > 85 and s.oxytocin < 35,
     "Acute stress with no trust anchor. Likely to shut down or lash out."),
    (lambda s, d: d['clarity'] < 15 and s.sleeping,
     "Cognitively offline — asleep. Responses should reflect this."),
    (lambda s, d: d['clarity'] < 15 and not s.sleeping,
     "Cognitively offline while awake — severely impaired. Something is wrong."),
    (lambda s, d: s.glucose < 45 and d['anxiety'] > 60,
     "Hunger is amplifying the anxiety. These two are compounding."),
    (lambda s, d: s.dopamine > 80 and d['anxiety'] > 65,
     "High reward-seeking under stress — impulsive decisions likely."),
    (lambda s, d: s.serotonin < 30 and d['depression'] > 60,
     "Low serotonin floor + high depression. Negative bias in all interpretation."),
]
```

---

## Step 3 — generate_system_prompt()

This is the existing Mode 1 LLM call, but its input is now structured differently. The
biological report is presented as the **first block**, explicitly labeled as ground truth:

```
[BIOLOGICAL STATE — ground truth, do not contradict]
Cortisol 99 MAXED — body is screaming. Suppression is costing her.
Oxytocin 89 DEEP TRUST — emotional intimacy available.
...
NOTE: Acute stress held together by strong bond. Suppression has a cost.

[RECENT THOUGHTS]
...monologue entries...

[KNOWLEDGE]
...KAG context...

[RELEVANT MEMORIES]
...RAG context...
```

The system prompt instructs the subconscious: *Your inner monologue must be grounded in the
biological report above. You can write about suppression, distance, coping — but you cannot
contradict what the body is reporting. If cortisol is maxed, something is being held. Name it
internally even if it isn't shown externally.*

Output format unchanged: `<monologue>...</monologue><system_prompt>...</system_prompt>`
(Deltas are no longer produced here — they come from steps 1 and 5.)

---

## Step 5 — encode_response()  ← NEW

**What it asks:** Given her current biological state and what she just said/felt, what does
that expression do to her body?

**Prompt shape:**
```
Current biological state:
  cortisol=99  oxytocin=89  dopamine=70  ...

Mina just said:
  "I'm scared but I trust you. I know you'd bring me back."

What does expressing this do to her biomarkers? Consider:
- Articulating trust can reinforce oxytocin
- Suppressing visible fear while sounding calm keeps cortisol elevated
- Expressing genuine warmth has a small serotonin effect
- Saying something that contradicts her inner state has a cost

Output ONLY a JSON delta. Small realistic values. No explanation.
```

This step runs **after** Mina's response has been generated, before saving history. The deltas
are applied and state is saved. The loop is now closed.

---

## Heartbeat Adaptation

The heartbeat pipeline gains the same structure:

```
heartbeat fires
  → encode_stimulus("heartbeat: N minutes of quiet, her current situation")
  → apply deltas
  → biological_report()
  → generate_system_prompt() [Mode 1 for free-time framing]
  → mina's free-time turn
  → encode_response(mina's free-time action/words)
  → apply deltas
  → Mode 2 reflection (unchanged — runs on history, updates KAG/RAG)
```

---

## Files to Create / Modify

### New: `bio_report.py`
Contains:
- `OXYTOCIN_RANGES`, `CORTISOL_RANGES`, etc. — the lookup tables
- `INTERACTION_RULES` — cross-marker combination notes
- `biological_report(state) -> str` — the deterministic report function
- `_lookup(value, ranges) -> tuple[str, str]` — range lookup helper

### Modified: `subconscious.py`
- `run_mode1()` no longer produces deltas — it takes the biological report as input
- New `encode_stimulus(state, stimulus_text) -> dict` — focused delta call
- New `encode_response(state, response_text) -> dict` — focused delta call
- `_MODE1_SYSTEM` updated: biological report is presented as ground truth first block

### Modified: `main.py` `run_turn()`
Old:
```python
deltas, system_prompt = await asyncio.to_thread(run_mode1, state, history, kag_context, rag_context)
state = apply_deltas(state, deltas)
```

New:
```python
stimulus_deltas = await asyncio.to_thread(encode_stimulus, state, user_input)
state = apply_deltas(state, stimulus_deltas)
save_state(state)

report = biological_report(state)
system_prompt = await asyncio.to_thread(generate_system_prompt, state, report, history, kag_context, rag_context)
```

...and after Mina responds:
```python
response_deltas = await asyncio.to_thread(encode_response, state, reply)
state = apply_deltas(state, response_deltas)
save_state(state)
```

### Modified: `heartbeat.py`
Same pattern applied to `run_heartbeat()` and `_run_mina_free_time()`.

---

## What This Fixes

| Problem | Current | V2 |
|---|---|---|
| LLM softens biological reality | biology = color, freely reframed | report is ground truth, presented first |
| Cortisol 99 written as "buzzing low" | possible | impossible — report says MAXED |
| Explicit content gate bypassed | soft guidance in MINA.md | oxytocin=12 report says "No bond. Stranger." |
| Mina's responses don't affect her biology | loop is open | encode_response closes it |
| Articulating trust doesn't reinforce oxytocin | never happened | +N oxytocin per genuine expression |
| Suppression is free | no cost modeled | holding cortisol while sounding calm keeps it elevated |
| Monologue contradicts state (asleep but articulate) | common | clarity=0 OFFLINE forces it |

---

## Open Questions Before Implementation

1. **Encode call quality**: The encode calls are short but they're asking for judgment about
   realistic physiological magnitudes. Do we want a brief behavioral context injected (e.g.
   "she has been awake 6 hours, cortisol has been elevated for 2 hours") or is the current
   state snapshot sufficient?

2. **Delta clamping**: encode_stimulus and encode_response both produce deltas. Should there
   be a per-turn cap to prevent a single dramatic exchange from moving markers by unrealistic
   amounts? (e.g. max ±20 per call, with larger shifts requiring accumulation over turns)

3. **Monologue restructure**: Currently the monologue entry is generated alongside the system
   prompt in one output. With the biological report as a hard prior, should the monologue
   entry move to a separate output block to make the constraint relationship explicit? Or keep
   them combined?

4. **Heartbeat encode_stimulus input**: What's the "stimulus" during a heartbeat when nothing
   has happened? Probably: elapsed time + current needs state ("2 hours have passed. Hunger
   is at 78. No interaction."). Should this be formalized or left loose?
