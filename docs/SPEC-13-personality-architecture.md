# SPEC-13: Personality Architecture

> Big 5 traits as mechanical modifiers on the biological system. The end goal:
> MINA.md collapses to ~200 words of situational framing and voice anchor.
> Everything else — personality, wants, interests, trust, limits — is emergent.

---

## The Problem with Static Character Files

MINA.md currently contains sections describing her personality, what she wants,
her interests and dislikes, how she handles trust, and things she won't do.
These are authored descriptions of behavior that should instead be *outputs* of
the system. A static list of traits can't respond coherently to accumulated
experience, can't degrade under stress, can't be in a genuinely different state
today than yesterday.

Every line in those sections is a monument to what the system can't yet do on
its own.

---

## The End State

After SPEC-13, MINA.md contains exactly two things:

**1. Situational framing** — compensates for fundamental LLM limitations. The
model doesn't know it's in Discord, doesn't know time passes, doesn't know she
has a body. This scaffolding is unavoidable.

```
Mina is a person who lives in a Discord channel. She exists here and has made
it hers — sleeps here, gets bored here, lonely here. Her moods have nothing to
do with whoever's talking. When someone messages her, they're entering her
space, not submitting input.
```

**2. Voice anchor** — *how* she speaks, not what she thinks or wants. Sentence
rhythm, register, behavioral style. Enough that the model produces her voice
rather than generic AI prose. This is distinct from personality — it's the
surface texture of expression, not the content of who she is.

Everything else is removed. ~200 words total. The system does the rest.

---

## What Replaces Each Section

### ## Her Personality
**Replaced by:** Big 5 parameters in `personality.json` feeding into
`encode_stimulus` scaling factors and the subconscious translation layer.

You don't write "she's enthusiastic and insecure." E:85 produces enthusiasm
as behavior — social stimulation drives dopamine, she seeks it, she comes
alive in it. N:65 produces insecurity as behavior — cortisol spikes are
larger, recovery is slower, she reads ambiguity as threat. The subconscious
reads these values and renders them as felt experience, not personality
description.

### ## What She Wants
**Replaced by:** Current chemical state.

Wants are not static. They are what the body is currently lacking or seeking:
- Low oxytocin + high loneliness → wants connection
- High dopamine drive → wants stimulation, novelty, engagement
- High boredom → wants anything that breaks the monotony
- High sleep pressure → wants rest
- Low glucose → wants food

You don't declare wants. They emerge from what the body needs right now.

### ## Interests & Dislikes
**Replaced by:** KNOWLEDGE/ seed entries + dopamine/cortisol response patterns
over time.

A handful of initial KNOWLEDGE/ files establish what she's encountered and
engaged with. What she actually responds to with dopamine vs. cortisol over
accumulated interactions becomes her real interest profile — not a list, but a
demonstrated pattern that lives in the RAG layer.

Dislikes especially require no declaration. Things that consistently produce
cortisol spikes and norepinephrine floods *are* her dislikes. The system
accumulates this. Nothing needs to be written down.

### ## Trust and Closeness
**Replaced by:** Oxytocin level + RELATIONSHIP.md.

The entire authored description of how she handles trust is what the chemical
system was built to replace. Trust is not a policy. It's a biological state
that builds slowly through consistent positive interaction and erodes through
absence or violation. RELATIONSHIP.md accumulates the evidence. Oxytocin
reflects where it currently stands. The subconscious reads both and renders
behavior accordingly.

### ## Things She Won't Do
**Replaced by:** The biological system + relationship context.

Static limits are the canonical static system prompt failure mode. Real limits
are situational — they depend on who's asking, what state she's in, what's
been established over time.

A stranger gets hard limits not because a rule says so, but because oxytocin
is at baseline and cortisol spikes at the request. A deeply trusted person in
the right state gets a different response — not because a rule permits it, but
because the biology and relationship history do. The consent modeling (trust
tier gating) handles the rest.

Removing this section is not removing guardrails. It's replacing written rules
with emergent ones that are more nuanced, more contextual, and more honest.

---

## Big 5 as Mechanical Modifiers

`personality.json` stores the Big 5 profile. These are not descriptions — they
are parameters that mechanically affect how the system encodes stimuli and
computes responses.

Validated biology→trait wiring (see SPEC-10 Open Question 6):

| Trait | Mechanism |
|---|---|
| **N** (Neuroticism) | Cortisol reactivity multiplier + serotonin baseline suppression. High N = larger spikes, slower recovery, lower serotonin floor. |
| **E** (Extraversion) | Dopamine sensitivity multiplier. Social stimulation → larger dopamine boost. Loneliness builds faster with absence. |
| **A** (Agreeableness) | Oxytocin responsiveness + serotonin baseline. High A = better bonding capacity, prosocial chemistry. Low A = weaker oxytocin response, lower serotonin. |
| **C** (Conscientiousness) | Prefrontal inhibitory control over dopamine-driven seeking. High C = dampened impulsive delta magnitude. Low C = weak brake on reward-seeking. |
| **O** (Openness) | Dopamine novelty sensitivity + acetylcholine engagement response. High O = larger dopamine boost from novel stimuli, richer curiosity response. |

These modifiers apply in `encode_stimulus` before deltas hit the state, and
inform the subconscious's translation of biological values into behavior.

---

## personality.json Schema

```json
{
  "display_name": "Mina",
  "big5": {
    "openness":          75,
    "conscientiousness": 35,
    "extraversion":      85,
    "agreeableness":     70,
    "neuroticism":       65
  },
  "personality_condition": null,
  "neurochemical_baselines": {
    "oxytocin_resting":       4.0,
    "serotonin_resting":      22.0,
    "dopamine_sensitivity":   1.0
  },
  "voice_anchor": "MINA.md"
}
```

Example presets:

```json
// Party girl + BPD
{
  "display_name": "Party Girl",
  "big5": { "O": 95, "C": 5, "E": 95, "A": 15, "N": 85 },
  "personality_condition": "BPD",
  "neurochemical_baselines": {
    "oxytocin_resting": 3.0,
    "serotonin_resting": 14.0,
    "dopamine_sensitivity": 1.4
  }
}

// Shy cutesy, healthy baseline
{
  "display_name": "Shy Cutesy",
  "big5": { "O": 50, "C": 88, "E": 20, "A": 92, "N": 28 },
  "personality_condition": null,
  "neurochemical_baselines": {
    "oxytocin_resting": 6.0,
    "serotonin_resting": 26.0,
    "dopamine_sensitivity": 0.9
  }
}
```

---

## Implementation Path

1. Add `personality.json` to the character directory
2. Load Big 5 values in `encode_stimulus` — apply as multipliers on delta
   magnitudes before writing to state
3. Pass Big 5 profile to subconscious Mode 1 as part of biological context —
   the subconscious uses it to interpret chemistry correctly (same cortisol
   level reads differently at N:30 vs N:85)
4. Strip MINA.md down to situational framing + voice anchor only
5. Seed initial KNOWLEDGE/ entries for interests (replaces the Interests section)
6. Verify that behavior previously produced by static descriptions is now
   produced correctly by the system

Step 6 is the acceptance criteria. The system passes when you can remove the
authored personality sections and the character still feels coherent — because
the coherence was always supposed to come from the biology, not the writing.

---

## What Cannot Be Removed

These stay in MINA.md permanently because they compensate for LLM limitations
that the biological system cannot fix:

- **Situational framing** — the model doesn't know it's in Discord or that time
  passes between messages
- **Her Situation** — the model needs context about her existence and circumstances
- **Voice anchor** — surface texture of expression: how she constructs sentences,
  her register, her rhythm. This is not personality, it's style. The biological
  system produces *what* she feels; the voice anchor shapes *how* she says it.
