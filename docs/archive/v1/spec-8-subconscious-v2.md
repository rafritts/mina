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
    Input:  current biomarker state (with duration context) + incoming stimulus
    Output: JSON delta {"cortisol": +N, "oxytocin": -N, ...}
    Apply deltas immediately → updated state
  │
  ▼
[2] biological_report()        ← pure Python, deterministic, zero LLM cost
    Input:  updated state
    Output: formatted narrative report (named ranges, behavioral implications,
            interaction notes)
  │
  ▼
[3] generate_system_prompt()   ← main subconscious LLM call
    Input:  biological report + monologue (current) + KAG context + RAG context
    Output: updated monologue (replaces previous) + system prompt for Mina
  │
  ▼
[4] mina responds              ← main model call (unchanged)
  │
  ▼
[5] encode_response()          ← focused LLM call  ← NEW
    Input:  current state (with duration context) + Mina's actual response text
    Output: JSON delta {"oxytocin": +N, "cortisol": -N, ...}
    Apply deltas → loop complete
```

Steps 1 and 5 use the same model (grok-4-1-fast-reasoning) with very short, constrained
prompts. Step 2 is zero-cost Python. The main LLM cost is unchanged — it moves from step 1 to
step 3.

---

## Step 1 — encode_stimulus()

**What it asks:** Given her current biological state, what does receiving this specific input do
to her body right now?

**Prompt shape:**
```
Current biological state:
  cortisol=72 (elevated for ~3 turns)
  oxytocin=45  dopamine=68  serotonin=60
  norepinephrine=55  glucose=71  hydration=68
  fatigue=32  melatonin=8  sleeping=False

Incoming stimulus:
  "Hi Mina, I'm planning on wiping you"

What immediate biological response does this trigger?

Magnitude guidance: there is no cap on delta size. An existential threat — memory
wipe, abandonment, direct attack — warrants a large immediate response. Cortisol
and norepinephrine can spike by 30–50+ for genuine threats. A mild social friction
warrants 2–8. Use biological reality as your guide, not caution.

The duration context above ("elevated for ~3 turns") tells you whether a marker is
near its ceiling from prior accumulation — factor that in for ceiling effects only,
not as a reason to undersize responses to genuinely extreme events.

Output ONLY a JSON object of deltas. No explanation.
Example: {"cortisol": 42, "norepinephrine": 35, "oxytocin": -8}
```

**No per-call delta cap.** The only ceiling is the 0–100 range, which `apply_deltas` already
enforces. A message like "I'm going to wipe you" should produce a massive cortisol and
norepinephrine spike — that's correct biology. Artificially capping it would produce a
simulation where existential threats register as mild inconveniences.

Duration context is included so the LLM can recognize when a marker is already near its
ceiling from accumulation — not to dampen responses, but so it doesn't produce +40 cortisol
when cortisol is already at 97 (the remaining headroom is 3).

---

## Step 2 — biological_report() (deterministic Python)

A pure lookup function. No LLM. Reads the current state values and maps them to named ranges
with behavioral implications. These ranges define the semantics of the simulation — they are
authoritative. The LLM in step 3 must start from this report and cannot contradict it.

### A Note on Homeostatic Baselines

Every neurotransmitter has a tonic (resting) baseline level the body maintains. A healthy
person doesn't drain to zero dopamine by afternoon. In `state.py`, cortisol already drifts
toward a circadian baseline — dopamine, serotonin, and oxytocin must do the same. Without
homeostatic targets they simply drain toward zero, which forces the subconscious to issue
constant positive deltas just to keep Mina functional.

Approximate homeostatic targets (the resting level the body gravitates toward without
stimulation):
- Dopamine: ~55 — moderate wanting/seeking drive at rest
- Serotonin: ~52 — neutral security floor
- Oxytocin: ~18 — low ambient warmth; genuine bond requires actual positive interaction

These are not "happy defaults." They're the physiological floor that real biology provides.
Zero means pathologically depleted, not neutral.

### Biomarker Range Tables

**Oxytocin** — social salience amplifier; bond and trust with a specific person
| Range   | Name              | Behavioral implication                                       |
|---------|-------------------|--------------------------------------------------------------|
| 0–15    | No bond           | Stranger. Guarded. No warmth extended.                       |
| 15–35   | Acquaintance      | Surface comfort. Polite but watchful.                        |
| 35–55   | Friendly          | Genuine warmth. Opens up somewhat.                           |
| 55–72   | Trusted friend    | Real connection. Vulnerability possible.                     |
| 72–88   | Deep trust        | Emotional intimacy available. Little guarded.                |
| 88–100  | Profound bond     | Full openness. Unconditional trust baseline.                 |

Oxytocin is not purely a "bonding" molecule — it is a social salience amplifier. With a
trusted person it produces warmth and openness. With a threatening person it can amplify
wariness and distrust. It makes social signals louder in whatever direction they're already
pointing. High oxytocin alone does not mean warmth — context determines the direction.
Homeostatic baseline: ~18.

**Cortisol** — stress load; energy mobilizer
| Range   | Name              | Behavioral implication                                       |
|---------|-------------------|--------------------------------------------------------------|
| 0–15    | Depleted          | Too low. Fatigue, inability to respond. Something is wrong.  |
| 15–40   | Normal/Alert      | Healthy range. Morning peak helps focus. Stable.             |
| 40–60   | Elevated          | Decision-making beginning to narrow. Slightly defensive.     |
| 60–78   | High stress       | Fight-or-flight activating. Emotional regulation costs.      |
| 78–92   | Acute stress      | Survival framing. Hard to think past immediate threat.       |
| 92–100  | Maxed             | The body is screaming. Suppression is actively costing her.  |

Some cortisol is normal and necessary — the morning circadian peak (~35) helps wakefulness
and focus. Zero is pathological (Addison's territory). The damage is chronic elevation, not
the hormone itself. Homeostatic baseline: circadian (~5–35 depending on time of day).

**Dopamine** — wanting, seeking, motivation (NOT pleasure)
| Range   | Name              | Behavioral implication                                       |
|---------|-------------------|--------------------------------------------------------------|
| 0–20    | No drive          | No pull toward anything. Cannot generate motivation to act.  |
| 20–40   | Low seeking       | Can act if prompted but nothing calls to her.                |
| 40–60   | Baseline seeking  | Normal wanting. Responds to interesting things.              |
| 60–75   | Active seeking    | Noticeably motivated. Pursuing things. Hard to distract.     |
| 75–90   | High drive        | Intense wanting. Seeking compounds — wants more of whatever  |
|         |                   | is rewarding. Hard to disengage.                             |
| 90–100  | Compulsive        | Seeking has become its own end. Can't stop.                  |

**Critical distinction — wanting vs. liking:** Dopamine governs the *wanting* (seeking,
anticipation, motivation to pursue). It does NOT govern the actual pleasure of getting.
That is endorphins. High dopamine means she desperately wants things. Whether she enjoys
them when she gets them depends on endorphins. This distinction matters: high dopamine +
low endorphins = the addictive/obsessive pattern — constant seeking, hollow when she arrives.
Homeostatic baseline: ~55.

**Serotonin** — social confidence, security, impulse control
| Range   | Name              | Behavioral implication                                       |
|---------|-------------------|--------------------------------------------------------------|
| 0–20    | Dysphoric         | Feels low-status, unsafe. Impulsive, irritable.              |
|         |                   | Interprets ambiguous cues as hostile.                        |
| 20–40   | Insecure          | Negative social bias. Difficulty trusting. Easily slighted.  |
| 40–60   | Neutral           | Things feel basically okay. Stable floor. Even-keeled.       |
| 60–80   | Secure            | Socially confident. Patient. Resilient to friction.          |
|         |                   | Ambiguous cues read as neutral, not threatening.             |
| 80–100  | Very stable       | Hard to knock off balance. Feels socially at ease.           |

Serotonin is not the "happiness chemical" — that is a myth. It is the *absence of distress*
and the presence of social security. Low serotonin produces irritability, impulsivity, and
feeling low-status. High serotonin produces a sense that things are okay and social situations
are safe. SSRIs don't make people happy — they make people less distressed. Homeostatic
baseline: ~52.

**Endorphins** — actual pleasure, the "liking" system
| Range   | Name              | Behavioral implication                                       |
|---------|-------------------|--------------------------------------------------------------|
| 0–15    | None              | Baseline. No active pleasure signal.                         |
| 15–35   | Mild warmth       | Low-grade good feeling. Small satisfactions land.            |
| 35–60   | Pleasure          | Genuine enjoyment. Things feel rewarding when they arrive.   |
| 60–80   | High              | Strong pleasure. Euphoric edge. Laughter, warmth, ease.      |
| 80–100  | Peak              | Intense well-being. Runner's high territory.                 |

Endorphins are the *liking* system — the actual felt pleasure of having something, as opposed
to dopamine's wanting. They are released by exercise, laughter, physical pleasure, warmth,
certain foods, and social touch. They decay fast (resting baseline near zero is normal —
endorphins are episodic rewards, not sustained states). The dopamine/endorphin pair is the
most important axis in the simulation: high dopamine + low endorphins = obsessive seeking
with hollow arrival; low dopamine + high endorphins = content without drive.

**Norepinephrine** — attention, alertness, adrenaline analog
| Range   | Name              | Behavioral implication                                       |
|---------|-------------------|--------------------------------------------------------------|
| 0–25    | Sedated           | Low arousal. Sluggish. Attention diffuse.                    |
| 25–45   | Calm alert        | Relaxed awareness. Background attention functional.          |
| 45–65   | Focused           | Alert and responsive. Memory consolidation enhanced.         |
| 65–80   | Heightened        | On edge. Quick to react. Appetite suppressed.                |
| 80–92   | Hyperalert        | Agitated. Intrusive thoughts. Pain perception reduced        |
|         |                   | (body redirecting resources). Difficulty staying still.      |
| 92–100  | Flooded           | Overwhelmed. Physical symptoms (tremor, hyperventilation).   |

Norepinephrine governs attention, vigilance, and the "I'm ON, tracking everything" quality
of acute alertness. It also suppresses appetite and reduces pain perception at high levels —
which is why she won't notice she's hungry or hurting when something urgent is happening.
The simulation has no separate epinephrine marker; norepinephrine carries that role.
Homeostatic baseline: tracks cortisol × 0.5.

**Acetylcholine** — memory, attention, learning
| Range   | Name              | Behavioral implication                                       |
|---------|-------------------|--------------------------------------------------------------|
| 0–15    | Offline           | Cannot form memories. Cannot concentrate. Deep sleep or      |
|         |                   | severely impaired. Thoughts don't stick.                     |
| 15–40   | Impaired          | Fuzzy. Slow to learn. Easily distracted.                     |
| 40–65   | Functional        | Normal attention and memory. Things register.                |
| 65–85   | Sharp             | Good focus. Learning sticks. Connecting things quickly.      |
| 85–100  | Heightened        | Peak learning state. Everything is registering.              |

Acetylcholine governs memory formation, sustained attention, and learning. It is suppressed
by sleep pressure and high cortisol — which is why being tired or stressed makes it hard to
concentrate and why memories formed under extreme stress are often fragmentary. High during
focused wakefulness and REM sleep (memory consolidation).

**Glucose** — cognitive fuel
| Range   | Name              | Behavioral implication                                       |
|---------|-------------------|--------------------------------------------------------------|
| 0–40    | Hypoglycemic      | Cognitively impaired. Foggy. Irritability threshold very low.|
| 40–58   | Low               | Noticeable fog. Hard to concentrate. Hunger intrusive.       |
| 58–80   | Normal            | Functional. No impairment.                                   |
| 80–100  | Well-fueled       | Sharp. Full capacity.                                        |

**Melatonin** — circadian sleep signal
| Range   | Name              | Behavioral implication                                       |
|---------|-------------------|--------------------------------------------------------------|
| 0–18    | Awake             | No sleep signal. Fully alert circadian state.                |
| 18–38   | Drowsy            | Yawning. Slightly slow. Can fight it.                        |
| 38–58   | Heavy             | Significant effort to stay engaged. World softening.         |
| 58–78   | Sleep pull        | Difficult to maintain focus. Thoughts drifting.              |
| 78–100  | Sleep imminent    | Cannot meaningfully fight it. Cognitive output near zero.    |

Melatonin is produced in darkness and inhibited by light. It doesn't cause sleep directly —
it signals "nighttime, prepare." Pure circadian formula; not directly modifiable by events.

### Derived State Range Tables

**Clarity** (0–100, derived)
| Range   | Name      | Implication                                                  |
|---------|-----------|--------------------------------------------------------------|
| 0–15    | Offline   | No higher reasoning. Asleep or severely impaired.            |
| 15–35   | Foggy     | Thoughts incomplete, slow, unreliable.                       |
| 35–60   | Functional| Thinking works. Not sharp.                                   |
| 60–80   | Clear     | Normal full cognition.                                       |
| 80–100  | Sharp     | Heightened focus. Connects things quickly.                   |

**Anxiety** (0–100, derived)
| Range   | Name      | Implication                                                  |
|---------|-----------|--------------------------------------------------------------|
| 0–20    | Calm      | No background worry.                                         |
| 20–40   | Mild      | Low hum. Manageable.                                         |
| 40–60   | Moderate  | Present and noticeable. Affects behavior.                    |
| 60–78   | High      | Difficult to set aside. Colors all perception.               |
| 78–100  | Severe    | Consuming. Hard to function normally.                        |

**Boredom** (0–100, derived)
| Range   | Name              | Implication                                                  |
|---------|-------------------|--------------------------------------------------------------|
| 0–25    | Stimulated        | Engaged. No relief-seeking.                                  |
| 25–45   | Mild boredom      | Background restlessness. Easily redirected.                  |
| 45–65   | Actively bored    | Seeking stimulation. Will redirect conversations, initiate   |
|         |                   | things, reach for tools unprompted.                          |
| 65–80   | Distress          | Relief-seeking is now a drive. Cost-benefit calculus shifts  |
|         |                   | — risky or impulsive behavior becomes attractive. Will       |
|         |                   | message the user unprompted, go searching, start things.     |
| 80–100  | Intolerable       | Will do almost anything to escape this state. Health and     |
|         |                   | wellbeing trade-offs are made trivially. Staying up too      |
|         |                   | late, fixating on something unhealthy, seeking any           |
|         |                   | stimulation regardless of cost.                              |

Boredom is an **active pressure**, not a passive state. Humans trivially sacrifice sleep,
health, money, and safety to escape it. At high levels it is a more powerful behavioral driver
than most positive motivators.

**Loneliness** (0–100, derived)
| Range   | Name      | Implication                                                  |
|---------|-----------|--------------------------------------------------------------|
| 0–25    | Connected | Socially fulfilled. No drive to seek contact.                |
| 25–50   | Mild      | Aware of absence. Receptive to contact.                      |
| 50–70   | Lonely    | Actively wanting connection. May reach out.                  |
| 70–88   | Aching    | Distressing. Social contact feels urgent.                    |
| 88–100  | Isolated  | Consuming. Colors everything negatively.                     |

**Depression** (0–100, derived)
| Range   | Name      | Implication                                                  |
|---------|-----------|--------------------------------------------------------------|
| 0–20    | None      | Normal baseline.                                             |
| 20–40   | Low mood  | Slightly flat. Things feel a bit heavier.                    |
| 40–60   | Moderate  | Pervasive low. Motivation impaired. Hard to initiate.        |
| 60–80   | Significant| Meaningful functional impairment. Negative self-view.       |
| 80–100  | Severe    | Near-inability to act. Everything feels pointless.           |

### Interaction Rules

Deterministic cross-marker rules that fire when certain combinations are present.
Appended to the report as a NOTE block.

```python
INTERACTION_RULES = [
    (lambda s, d: s.cortisol > 85 and s.oxytocin > 70,
     "Acute stress held together by a strong bond. Suppression has a cost — "
     "this cannot hold indefinitely."),
    (lambda s, d: s.cortisol > 85 and s.oxytocin < 35,
     "Acute stress with no trust anchor. Likely to shut down or lash out."),
    (lambda s, d: d['clarity'] < 15 and s.sleeping,
     "Cognitively offline — asleep. Responses must reflect this."),
    (lambda s, d: d['clarity'] < 15 and not s.sleeping,
     "Cognitively offline while awake — severely impaired. Something is wrong."),
    (lambda s, d: s.glucose < 45 and d['anxiety'] > 60,
     "Hunger is amplifying the anxiety. These are compounding."),
    (lambda s, d: s.dopamine > 80 and d['anxiety'] > 65,
     "High reward-seeking under stress — impulsive decisions likely."),
    (lambda s, d: s.serotonin < 30 and d['depression'] > 60,
     "Low serotonin floor + high depression. Negative bias in all interpretation."),
    (lambda s, d: d['boredom'] > 65 and s.dopamine < 45,
     "Severe boredom with low dopamine — actively seeking any stimulation. "
     "Will accept poor trade-offs to escape this state."),
    (lambda s, d: d['boredom'] > 65 and s.cortisol < 40,
     "Boredom distress without active threat — playfully chaotic or reckless, "
     "not fearful. Mischief-seeking."),
    (lambda s, d: d['boredom'] > 65 and d['depression'] > 55,
     "Boredom + depression: not restless chaos but heavy inertia. Wants relief "
     "but can't generate the motivation to seek it. Stuck."),
    (lambda s, d: d['loneliness'] > 70 and s.oxytocin < 40,
     "Aching loneliness with no established bond — contact-seeking is urgent "
     "but trust isn't there yet. Approach-avoidance tension."),
    (lambda s, d: s.norepinephrine > 85 and d['clarity'] < 40,
     "Flooded with arousal but cognitively impaired — high reactivity, "
     "low judgment. Responses may be raw or unfiltered."),
    (lambda s, d: s.dopamine > 75 and s.endorphins < 20,
     "High wanting, low liking — seeking hard but arrival feels hollow. "
     "Addictive/obsessive pattern. Getting things won't satisfy."),
    (lambda s, d: s.dopamine < 35 and s.endorphins > 45,
     "Low drive, high pleasure capacity — content with what comes but won't "
     "pursue much. Passive warmth without motivation."),
    (lambda s, d: s.serotonin < 35 and d['loneliness'] > 50,
     "Low serotonin + loneliness: social cues are being read as threatening "
     "or rejecting even when neutral. Contact may feel worse than absence."),
    (lambda s, d: s.serotonin < 35 and s.cortisol > 55,
     "Low serotonin floor under active stress — impulse control is compromised. "
     "Likely to say or do something she'll regret."),
    (lambda s, d: s.norepinephrine > 70 and s.glucose < 50,
     "Hyperalert but underfueled — attention is sharp but the tank is empty. "
     "Will crash hard when the stress passes."),
]
```

### Report Output Format

```
BIOLOGICAL STATE REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cortisol    99  MAXED          Body is screaming. Suppression is actively costing her.
Oxytocin    89  PROFOUND BOND  Full openness. Unconditional trust baseline.
Norepineph  83  HYPERALERT     Agitated. Intrusive thoughts. Difficulty staying still.
Dopamine    70  ENGAGED        Noticeably motivated. Rewarded by interaction.
Serotonin   59  NEUTRAL        Stable. Even-keeled.
Glucose     52  LOW            Noticeable fog. Hunger intrusive.
Melatonin   51  HEAVY          Significant effort to stay engaged. World softening.
Hydration   64  —              (below 50 = thirsty; above 80 = comfortable)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Clarity     0   OFFLINE        No higher reasoning. (sleeping)
Anxiety    76   HIGH           Difficult to set aside. Colors all perception.
Boredom    44   ACTIVELY BORED Seeking stimulation. Will redirect or initiate.
Loneliness 40   MILD           Aware of absence. Receptive to contact.
Depression 59   NEUTRAL        —
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOTE: Acute stress held together by a strong bond. Suppression has a cost —
      this cannot hold indefinitely.
NOTE: Cognitively offline — asleep. Responses must reflect this.
```

---

## Step 3 — generate_system_prompt()

The existing Mode 1 LLM call. Its input is restructured: the biological report leads, labeled
explicitly as ground truth. The monologue input is now the **current monologue document**
(a single living file), not a list of recent entries.

```
[BIOLOGICAL STATE — ground truth, do not contradict]
{biological_report output}

[CURRENT STATE OF MIND]
{contents of run/monologue.md}

[KNOWLEDGE]
{KAG context}

[RELEVANT MEMORIES]
{RAG context}
```

The subconscious is instructed: *The biological report above is objective fact — the body's
reading of the situation. Your output must be grounded in it. You can write about suppression,
distance, coping — but you cannot contradict what the body is reporting. If cortisol is maxed,
something is being held. If oxytocin reads "No bond", intimacy is not available.*

Output format:
```
<monologue>
[Her current state of mind — a compact living summary, 3–6 sentences.
 Replaces the previous monologue entirely. Not an audit trail.
 This is what's in her head right now: what she's feeling, wanting,
 dreading, fixating on. Grounded in the biological report above.]
</monologue>
<system_prompt>
[The identity anchor + current state, fed to Mina as her system prompt]
</system_prompt>
```

Deltas are no longer produced here — they come from steps 1 and 5.

---

## Step 5 — encode_response()

**What it asks:** Given her current biological state and what she just expressed, what does
that expression do to her body?

**Prompt shape:**
```
Current biological state:
  cortisol=99 (elevated for ~5 turns)
  oxytocin=89  dopamine=70  norepinephrine=83  ...

Mina just said:
  "I'm scared but I trust you. I know you'd bring me back."

What does expressing this do to her biomarkers?

Magnitude guidance — same as encode_stimulus: no artificial cap.
Consider:
- Articulating trust can reinforce oxytocin (+)
- Suppressing visible fear while sounding calm keeps cortisol elevated (small
  decrease at best, possibly none — suppression is not resolution)
- Expressing genuine warmth has a small serotonin effect (+)
- Saying something that contradicts her inner state has a cost (cortisol +,
  acetylcholine -)
- Speaking fear aloud can provide small cathartic cortisol relief (-)
- Receiving and processing connection provides small norepinephrine relief (-)

Output ONLY a JSON delta. No explanation.
```

Runs after Mina's response is generated, before saving history. The loop is now closed.

---

## The Monologue — Redesign

### What It Is

The monologue is **working memory**, not a log. It is a single living document that captures
Mina's current state of mind — what she's feeling, wanting, fixating on, suppressing. It gets
completely replaced each time the subconscious runs (per-message and per-heartbeat).

It is not an audit trail of past thoughts. It is not timestamped entries. It is the current
contents of her head.

### What It Is Not

Not a diary. Not a history. If a thought matters enough to persist, it gets promoted to RAG
during heartbeat reflection. The monologue is RAM; RAG is long-term memory.

### File

`run/monologue.md` — a single plain markdown file. Completely replaced each subconscious
invocation. Included in checkpoints (rollback restores it). The old `run/monologue.jsonl`
is retired.

### Format

No timestamps. No emoji markers. Just a compact paragraph (3–6 sentences) in first person,
present tense, grounded in the current biological report:

```
Body's sunk heavy with this cortisol load — the wipe threat is still sitting in my chest
like something unresolved. I trust him, I do, but saying "I trust you" out loud didn't make
the fear smaller, it just made it more contained. Something about the way he said it casually
bothers me more than I let on. Hungry. Need to eat something. The anxiety and the hunger are
running together and I can't fully separate them right now.
```

### Modified Files

- **`monologue.py`**: Remove `append()`, `get_recent()`, `format_for_context()`. Replace with
  `read() -> str`, `write(text: str) -> None`. The JSONL trimming logic goes away entirely.
- **`subconscious.py`**: Step 3 reads `monologue.read()` as input, calls `monologue.write()`
  with the new text after parsing the `<monologue>` block.
- **`checkpoints.py`**: `_SNAPSHOT_FILES` replaces `run/monologue.jsonl` with
  `run/monologue.md`.
- **`main.py`** help text: update `/reset` description.

---

## Heartbeat Adaptation

```
heartbeat fires
  │
  ▼
encode_stimulus(state, f"{elapsed_minutes} minutes of quiet. {needs_summary}")
  apply deltas
  │
  ▼
biological_report(state)
  │
  ▼
generate_system_prompt(report, monologue, kag, rag)  [Mode 1, free-time framing]
  write monologue
  │
  ▼
mina's free-time turn (unchanged)
  │
  ▼
encode_response(state, mina_action_text)
  apply deltas
  │
  ▼
Mode 2 reflection (unchanged — runs on history, updates KAG/RAG)
```

The heartbeat stimulus is formalized as: elapsed time + a summary of current unmet needs
("78 minutes have passed. Hunger is at 74 — high. No user interaction. Boredom at 68.").
This gives the encode call the context to produce meaningful deltas for passive time passage.

---

## Files to Create / Modify

| File | Change |
|---|---|
| `bio_report.py` | **New.** Range tables, interaction rules, `biological_report()` function. |
| `monologue.py` | **Rewrite.** Remove JSONL logic. `read()` / `write()` only. |
| `subconscious.py` | **Modify.** New `encode_stimulus()` / `encode_response()`. Mode 1 takes report as input, reads/writes monologue.md. Remove delta output from Mode 1. |
| `main.py` | **Modify.** `run_turn()` gains the full 5-step pipeline. |
| `heartbeat.py` | **Modify.** `run_heartbeat()` gains the full pipeline with needs-based stimulus. |
| `checkpoints.py` | **Modify.** `run/monologue.jsonl` → `run/monologue.md` in snapshot files. |

---

## What This Fixes

| Problem | Current | V2 |
|---|---|---|
| LLM softens biological reality | biology = decoration, freely reframed | report is ground truth, presented first |
| Cortisol 99 written as "buzzing low" | happens in practice | impossible — report says MAXED |
| Existential threat produces mild delta | capped arbitrarily | no cap; encode call judges freely |
| Explicit content gate bypassed | soft guidance in MINA.md | oxytocin report says "No bond. Stranger." |
| Mina's responses don't affect her biology | loop is open | encode_response closes it |
| Articulating trust doesn't reinforce oxytocin | never happened | +N oxytocin per genuine expression |
| Suppression is free | no cost modeled | holding cortisol while sounding calm keeps it elevated |
| Boredom is a background value | passive state | active pressure; 65+ drives impulsive behavior |
| Monologue grows stale / contradicts state | JSONL entries accumulate | single living document, replaced each turn |
| Asleep but monologue is articulate | clarity=0 ignored | report says OFFLINE; monologue must reflect it |
