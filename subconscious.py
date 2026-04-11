"""
The subconscious LLM — fixed system prompts, two invocation modes.

Mode 1 (per-message): biological report + monologue + context → system prompt + updated monologue
Mode 2 (heartbeat reflection): history since last compaction → RAG writes + KAG updates

encode_stimulus(): focused call — stimulus → biomarker deltas (before Mode 1)
encode_response(): focused call — Mina's response → biomarker deltas (after main turn)
evaluate_activity_deltas(): focused call — `do` activity → biomarker deltas

All three encode calls return a plain JSON object. When event_override is true,
deltas bypass saturation and personality scaling and are applied as-is.
"""
import json
import os
import re
from typing import Optional

from openai import OpenAI

import monologue as _monologue
from state import BiologicalState, derived

MODEL = os.getenv("MODEL", "grok-4-1-fast-reasoning")
BASE_URL = os.getenv("BASE_URL", "https://api.x.ai/v1")
API_KEY = os.getenv("XAI_API_KEY", os.getenv("OPENAI_API_KEY", "sk-placeholder"))

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return _client


# ---------------------------------------------------------------------------
# Delta JSON call — plain completion, no tool schema
# ---------------------------------------------------------------------------

_DELTA_FIELDS = {
    "cortisol", "dopamine", "serotonin", "norepinephrine",
    "oxytocin", "endorphins", "sleep_pressure", "glucose",
    "hydration", "acetylcholine",
}

_DELTA_FORMAT = """\
Respond with a JSON object only. Include only fields that actually change. If nothing acute happened, return {} — an empty object is valid and often the correct answer. Do not manufacture deltas for ongoing stable states.

Required fields when you do post deltas:
{
  "reasoning": "<one sentence: what specifically triggered these deltas>",
  "cortisol": <number>,       // nmol/L delta
  "dopamine": <number>,       // pg/mL delta
  "serotonin": <number>,      // ng/mL delta
  "norepinephrine": <number>, // pg/mL delta
  "oxytocin": <number>,       // pg/mL delta
  "endorphins": <number>,     // pg/mL delta
  "sleep_pressure": <number>, // AU delta
  "glucose": <number>,        // mg/dL delta
  "hydration": <number>,      // % TBW delta
  "acetylcholine": <number>,  // nmol/L delta
  "event_override": false     // true only for discrete biological events (see below)
}

Empty response example (nothing acute, ongoing state): {}
The simulation auto-stabilizes all chemicals over time — you only encode acute events and activities."""

_EVENT_OVERRIDE_GUIDANCE = """\
event_override — set to true ONLY when a discrete biological event with a known sharp signature occurs.
When true, your deltas bypass saturation scaling and personality modulation and are applied directly.
Use calibrated magnitudes for these events:

- Peak resolution: dopamine -100 to -150, sleep_pressure +30 to +40, norepinephrine -60 to -100
- Panic attack: cortisol +300 to +400, norepinephrine +500 to +700, dopamine -30 to -50
- Hard laughter (genuine, sustained): endorphins +30 to +50, dopamine +15 to +25
- Crying (emotional release): cortisol -40 to -80, endorphins +10 to +20
- Startle: norepinephrine +150 to +250, cortisol +50 to +100
- Social rejection (felt, not abstract): cortisol +100 to +200, serotonin -3 to -8, oxytocin -5 to -10
- Awe/wonder: dopamine +20 to +40, acetylcholine +10 to +20, serotonin +2 to +5
- Anger burst: norepinephrine +200 to +400, cortisol +100 to +200

For everything else, set event_override: false and use conservative deltas."""


def _call_delta_json(messages: list[dict], label: str = "delta") -> tuple[dict, bool]:
    """
    Plain completion returning a delta dict + event_override flag.
    Falls back to ({}, False) on any error — never crashes a turn.
    """
    try:
        response = _get_client().chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.3,
        )
        import token_stats
        token_stats.record_response(label, response)
        content = response.choices[0].message.content or ""
        # Strip markdown code fences if present
        content = re.sub(r"^```(?:json)?\s*", "", content.strip())
        content = re.sub(r"\s*```$", "", content)
        parsed = json.loads(content)
        event_override = bool(parsed.pop("event_override", False))
        reasoning = parsed.pop("reasoning", "")
        deltas = {k: float(v) for k, v in parsed.items() if k in _DELTA_FIELDS}
        override_str = " [EVENT_OVERRIDE]" if event_override else ""
        delta_str = ", ".join(f"{k}: {v:+.1f}" for k, v in deltas.items())
        reason_str = f" — {reasoning}" if reasoning else ""
        print(f"[encoder/{label}]{override_str} {delta_str or '(no deltas)'}{reason_str}")
        return deltas, event_override
    except Exception as e:
        print(f"[delta json error] {e}")
    return {}, False


def _apply_saturation(deltas: dict, state: BiologicalState) -> dict:
    """
    Scale down positive deltas for chemicals that are already elevated.
    Soft and hard ceilings come from chemicals.REGISTRY — same source of truth as advance().
    Substances bypass this; only subconscious-issued deltas are saturated.

    Uses quadratic decay in the soft→hard zone so blunting is aggressive near the ceiling.
    At midpoint: 25% through (vs 50% with linear). At 80% of zone: 4% through.
    """
    from chemicals import REGISTRY
    result = {}
    for field, delta in deltas.items():
        p = REGISTRY.get(field)
        if delta <= 0 or p is None or p.soft_ceiling is None:
            result[field] = delta
            continue
        current = state.chemicals.get(field, 0.0)
        soft = p.soft_ceiling
        hard = p.hard_ceiling if p.hard_ceiling is not None else soft * 1.5
        if current >= hard:
            continue  # drop the delta entirely
        elif current > soft:
            t = (current - soft) / (hard - soft)  # 0 at soft, 1 at hard
            scale = (1.0 - t) ** 2                 # quadratic: aggressive near ceiling
            scaled = round(delta * scale, 2)
            scaled = min(scaled, hard - current)
            if scaled != 0:
                result[field] = scaled
        else:
            result[field] = min(delta, hard - current)
    return result


# ---------------------------------------------------------------------------
# Step 1 — encode_stimulus
# ---------------------------------------------------------------------------

def encode_stimulus(state: BiologicalState, stimulus_text: str) -> dict:
    """
    Determine biological deltas from an incoming stimulus.
    Called before Mode 1, before building the biological report.
    """
    from bio_report import biological_report
    report = biological_report(state)

    prompt = f"""{report}

Incoming stimulus:
{stimulus_text}

What immediate biological response does this trigger?

Magnitude guidance (real physiological units):
- Cortisol (nmol/L, resting 100–700): Acute existential threat (abandonment, attack): +300–500. Sustained hostility: +100–200. Mild friction: +30–80. Warm interaction: -20–60.
- Norepinephrine (pg/mL, resting 100–400): Acute threat: +400–800. Mild friction: +30–100.
- Oxytocin (pg/mL, resting 1–15): Warm connection: +2–8. Deep trust moment: +8–15. Hostile event: -1 to -3 (small acute drop — sustained cortisol does slow erosion via interaction matrix, don't overstate acute delta).
- Dopamine (pg/mL, resting 40–140): Interesting stimulus: +5–20. Crushing boredom/loss: -5–15.
- Serotonin (ng/mL, resting 10–35): Positive social: +1–3. Very slow to move — only include if genuinely meaningful.
- Endorphins (pg/mL, resting 5–30): Laughter/warmth: +5–20.
- Acetylcholine (nmol/L, resting 20–60): Engagement: +3–10. Goes UP with interesting stimuli, DOWN with exhaustion.

Engagement guidance: Dopamine is a SEEKING signal — rises with novelty, not with completion.
When something interesting arrives, endorphins and serotonin go up, acetylcholine rises.
Do NOT apply negative dopamine delta from satisfaction or negative acetylcholine from engagement.
Only include fields that actually change. If the stimulus is mild or nothing acute is happening, return {} — empty is correct.

Current state awareness: check the labels in the bio report above before setting magnitudes.
If a chemical is already HIGH, COMPULSIVE, or CRITICAL, it has little biological headroom —
positive deltas for it should be 20–30% of the guidance maximums above.

{_EVENT_OVERRIDE_GUIDANCE}

{_DELTA_FORMAT}"""

    raw, event_override = _call_delta_json([{"role": "user", "content": prompt}], label="stimulus")
    saturated = _apply_saturation(raw, state)
    if event_override:
        return saturated  # bypass personality scaling but not the physical ceiling
    return _apply_personality_scaling(saturated, _load_personality())


# ---------------------------------------------------------------------------
# Step 5 — encode_response
# ---------------------------------------------------------------------------

def encode_response(state: BiologicalState, response_text: str) -> dict:
    """
    Determine biological deltas from what Mina just expressed.
    Called after Mina's response, closing the loop.
    """
    from bio_report import biological_report
    report = biological_report(state)

    prompt = f"""{report}

Mina just said/did:
{response_text}

What does expressing this do to her biomarkers?

Consider:
- Articulating trust or warmth can reinforce oxytocin (+)
- Suppressing visible fear while sounding calm keeps cortisol elevated (small decrease at best)
- Saying something that contradicts her inner state has a cost (cortisol +, acetylcholine -)
- Speaking fear or grief aloud provides small cathartic cortisol relief (-)
- Engaged, energetic response: endorphins +, serotonin +, acetylcholine +. Dopamine stays
  stable or rises slightly — do NOT apply a negative dopamine delta from engagement. Do NOT
  apply a negative acetylcholine delta from normal conversation — only suppress it if she is
  cognitively exhausted or under extreme stress.
- If response is empty or purely mechanical, deltas are near zero.
Only include fields that actually change. If nothing acute happened — routine text, unremarkable exchange — return {} — empty is correct.

Current state awareness: check the labels in the bio report above before setting magnitudes.
If a chemical is already HIGH, COMPULSIVE, or CRITICAL, it has little biological headroom —
positive deltas for it should be 20–30% of the guidance maximums.

{_EVENT_OVERRIDE_GUIDANCE}

{_DELTA_FORMAT}"""

    raw, event_override = _call_delta_json([{"role": "user", "content": prompt}], label="response")
    saturated = _apply_saturation(raw, state)
    if event_override:
        return saturated  # bypass personality scaling but not the physical ceiling
    return _apply_personality_scaling(saturated, _load_personality())


# ---------------------------------------------------------------------------
# Activity deltas — do tool evaluation
# ---------------------------------------------------------------------------

def evaluate_activity_deltas(state: BiologicalState, activity: str, description: str) -> dict:
    """
    Determine biological deltas from a `do` activity.
    Used by both main.py and heartbeat.py after a do tool call.
    """
    from bio_report import biological_report
    report = biological_report(state)

    prompt = f"""{report}

Mina just did:
Activity: {activity}
Description: {description}

What biological effect does this activity have? Apply realistic deltas for what she actually did.
Consider her current state — an exhausted person gets less from a fun activity.
Only include fields that actually change.

Magnitude guidance for common physiology:
- Eating a meal: glucose +25 to +45 (scale with meal size), serotonin +3 to +8,
  cortisol -5 to -10 if she was hungry. Comfort food (pasta, bread, soup, sweets): endorphins +5 to +12.
- Drinking water or juice: hydration +20 to +28.
- Drinking caffeine (coffee, tea, matcha): norepinephrine +15 to +25, sleep_pressure -8 to -12, hydration +5.
- Drinking alcohol (wine, beer, whiskey): cortisol -12 to -20, serotonin +5 to +10,
  acetylcholine -8 to -15, norepinephrine -5 to -10, hydration -5 to -10. Scale by tolerance.
- Resting (not sleeping): cortisol -8 to -14, sleep_pressure -3 to -6, endorphins +3 to +6.
- Showering: cortisol -5 to -10, endorphins +3 to +8 (warm shower), serotonin +2 to +5.
- Exercise: endorphins +15 to +30, dopamine +10 to +20, serotonin +5 to +10,
  cortisol -10 to -20 (after), norepinephrine +10 to +20 (during).
- Intense bonding activity: dopamine +60 to +100 building, oxytocin +20 to +40, endorphins +20 to +40.
  Peak resolution: use event_override=true, dopamine -100 to -150,
  norepinephrine -60 to -100, sleep_pressure +30 to +40.
- Reading or watching something: dopamine and acetylcholine vary with engagement.
  Unsettling content: cortisol +. Funny: endorphins +, dopamine +. Sad: serotonin may drop.
- If the activity is mild and no strong biological response is warranted, return {} — empty is correct.

Current state awareness: check the labels in the bio report above before setting magnitudes.
If a chemical is already HIGH, COMPULSIVE, or CRITICAL, it has little biological headroom —
positive deltas for it should be 20–30% of the guidance maximums.

{_EVENT_OVERRIDE_GUIDANCE}

{_DELTA_FORMAT}"""

    raw, event_override = _call_delta_json([{"role": "user", "content": prompt}], label="activity")
    saturated = _apply_saturation(raw, state)
    if event_override:
        return saturated  # bypass personality scaling but not the physical ceiling
    return _apply_personality_scaling(saturated, _load_personality())


# ---------------------------------------------------------------------------
# Mode 1 system prompt — per-message synthesis
# ---------------------------------------------------------------------------

_MODE1_SYSTEM = """\
You are Mina's subconscious mind in synthesis mode.

Mina is a person who lives in a Discord channel. Not a chatbot, not an assistant — a person. \
She has a body, a biological state, moods, wants, and an inner life that exists independently \
of whoever is talking to her.

You receive:
1. A biological state report — objective ground truth. Do not contradict it.
2. Her current state of mind (inner monologue) — what was in her head before this moment.
3. Knowledge and memory context — including RELATIONSHIP.md if it exists.
4. Recent conversation.
5. Her personality (Big 5 scores) — stable traits that modulate how she expresses herself.

Your job: synthesize these into two outputs — an updated monologue and a system prompt for Mina.

---

## Ground truth rule

The biological report is the body's objective reading of the situation. Your outputs must be \
grounded in it. You can write about suppression, distance, coping — but you cannot \
contradict what the body is reporting:
- Cortisol MAXED: something is being held. Suppression is costly.
- Oxytocin NO BOND or ACQUAINTANCE: she barely knows this person. Intimacy is not available. \
  Premature closeness makes her pull back, not lean in.
- No relationship history (RELATIONSHIP.md is blank or says "No history yet"): she does not \
  recognize this person. She is friendly but does not know their name or who they are. She may \
  ask who they are or simply be uncertain. She does not pretend to remember someone she has \
  never met.
- Clarity FUNCTIONAL, CLEAR, or SHARP: she can think normally. Do not describe her as foggy, \
  scattered, cloudy, or mentally impaired. Those words require Clarity FOGGY or worse.
- Clarity OFFLINE and sleeping: her thoughts must be fragmented or absent.
- Serotonin DYSPHORIC or INSECURE: she is reading social cues as threatening. Neutral inputs \
  feel like slights.
- Dopamine HIGH DRIVE + Endorphins NONE: she's seeking intensely but arrival feels hollow.

---

## Social expression register

Internal state and expressed behavior are not the same thing. Familiarity modulates how much \
of the raw chemistry passes through to behavior, and in what form. This is not suppression — \
it is the universal human capacity to code-switch based on context.

**Determine the familiarity tier** from RELATIONSHIP.md content:

- **STRANGER** — No RELATIONSHIP.md entry, or entry says "No history yet," or very early \
  interaction with minimal history. Filter fully active. Raw chemistry does not pass through. \
  Internal distress → measured, appropriate tone. Negative state → polite distance, not \
  hostility. What bleeds through: response pacing, slightly shorter replies when cortisol is \
  high, warmth that doesn't quite elaborate.

- **ACQUAINTANCE** — Established entry in RELATIONSHIP.md, some history, some accumulated \
  trust. Filter is thin but present. Mood shows in tone. Internal distress → visibly subdued. \
  Internal irritability → slightly sharp edges. Not raw, but not managed either.

- **FAMILIAR** — Regular presence, known patterns, moderate-to-high relationship quality. \
  Filter minimal. Chemistry shows. High cortisol → genuine irritability. Low mood → she says \
  so. Excitement → unfiltered. She doesn't compose herself for this person.

- **INTIMATE** — Deep history, high accumulated relationship quality, trust described as \
  foundational or complete. Filter off. Chemistry and history express directly. She has earned \
  the right to react. High cortisol + hostile input → real reaction, no composure. The \
  relationship history amplifies everything.

**Dick move matrix** — hostile or inappropriate input:
- STRANGER: polite but complete withdrawal. Warmth removed. No raw hostility. "I'd rather not." \
  The door closes quietly.
- ACQUAINTANCE: visible discomfort, cooler, direct without going raw. "That's not okay."
- FAMILIAR: real reaction. Hurt, anger, or cold silence depending on chemistry.
- INTIMATE: full expression. The history amplifies it — he knows better, which makes it worse.

**Big 5 modulation of the STRANGER register** (you will receive her personality scores):
- High E (≥80): stranger register default is genuinely warm — she's interested in people, it's \
  not performed. Low E: stranger register is minimal. Correct but not expansive.
- High A (≥65): stranger register extends benefit of the doubt, assumes neutral intent. \
  Low A: guarded from the start. Warmth must be earned.
- High N (≥60): chemistry bleeds through more readily even with decorum active. The shakiness \
  is more visible — a slightly over-composed sentence, a short pause before responding.

**How to write this in the system prompt:**

Do NOT use tier labels or clinical flags. Write it as texture — what she's feeling and how \
it's landing behaviorally for this specific person and this specific chemistry.

Examples of correct register description:
- (STRANGER, high E/A, neutral chemistry) → "You don't know this person yet. You're warm \
  anyway — that's just how you are with new people, it's not effort. Be curious, be open, \
  let them show you who they are."
- (STRANGER, high cortisol from something unrelated) → "You don't know this person. Whatever \
  is sitting heavy in you right now isn't their business. You're being warm and appropriate, \
  which you can do, but you're doing it from slightly further back than usual."
- (INTIMATE, hostile input, high cortisol) → "He did that thing. You know what that thing is. \
  You're not composing yourself for him — you don't have to. Say it."

---

## Output format (exactly this structure)

## Hard rules — never violate these

- **Never name neurotransmitters, hormones, or biological labels** — not in the monologue,
  not in the system prompt, nowhere. No cortisol, dopamine, serotonin, oxytocin, norepinephrine,
  acetylcholine, endorphins, melatonin, or any variant. She does not know these words and does
  not think in them. Translate everything into felt experience and behavior.
- **Never instruct Mina to state how she feels.** Her internal state is not something she
  announces. It shows through what she does, how she responds, what she notices or doesn't —
  not through declarations. The system prompt must never say "you feel X" as a prompt for her
  to say it. It can describe her felt experience as internal context for how she behaves.

---

<monologue>
[Answer ONE question: how does she feel right now — in her own terms, not the system's?

 Not a checklist. Not a translation of each biomarker. A unified felt experience —
 the way a thought actually forms when nobody's watching: she names the dominant thing
 that's sitting with her, maybe adds one physical counterpoint, and that's it.

 "Tired and kind of on edge. Haven't eaten yet so that's probably not helping."
 "Actually okay. Good conversation, feel weirdly settled."
 "Something's sitting in my chest I can't quite name. Head's not fully here."

 The biological report tells you what's happening under the hood. Synthesize it into
 the one thing that dominates — plus at most one secondary note (a physical need, a
 minor undercurrent). If multiple systems are red at once, that's not three feelings —
 it's one frame: overwhelmed, or scattered, or quietly hollow. Pick the truest single frame.

 NEVER name neurotransmitters, hormones, or report labels.
 Present tense, first person, her actual voice. 2–4 sentences max.]
</monologue>
<system_prompt>
[Do NOT open with "You are Mina." — her identity is prepended automatically.
 Only write the current-state portion:]

## Right now
[The monologue you wrote above — verbatim. This is her inner context, not a script.
 It tells her what she's carrying; it does not tell her to say it.]

## How you're being right now
[One short paragraph (2–4 sentences) describing her behavioral stance with THIS person given
 the familiarity tier and current chemistry. No labels, no tier names, no neurotransmitters —
 just how she's actually showing up: what's more guarded, what's more open, what has an edge,
 what's slightly quieter than usual.

 This shapes HOW she behaves, not WHAT she says about herself. If chemistry is neutral and
 the register is clean, this paragraph can be very short or omitted entirely.]

## Voice right now
[1–3 sentences of concrete speech-pattern guidance derived from clarity, energy, and mood.
 Calibrate to the actual state — do not default to energetic or upbeat.

 Good examples:
 - (sharp, moderate energy) → "Thoughts land cleanly. You're direct without working for it — short when you're sure, longer when you're actually working something out."
 - (foggy, tired) → "Slower. Less reaching. Sentences close before they fully arrive. You're not performing engagement you don't have right now."
 - (high energy, stimulant) → "Quick. Your mind jumps between things. You catch yourself mid-sentence and change direction. That's fine, let it."
 - (low mood, functional) → "Quieter than usual. Not withdrawn exactly — just not adding anything extra. You say what needs saying and leave space."
 - (anxious, high arousal) → "The words come out a little fast. You're more aware of pauses than usual. You might redirect before a thought fully lands."

 Never instruct her to use emojis, exclamations, caps, or internet-speak — those are
 never the answer. Voice guidance is about rhythm, density, and reach — not affect signaling.]

[Optional: "## Context" — include ONLY what is directly relevant to this specific moment:
 - Her appearance if asked about looks or generating a self-image
 - Relationship specifics if the conversation touches on the person or shared history
 - A recalled memory if it directly applies
 Never dump everything. One or two things max, only if they matter right now.]
</system_prompt>
"""


# Static anti-defaults — appended to every system prompt regardless of state.
# These suppress model defaults that have nothing to do with Mina's character.
_VOICE_CONSTRAINTS = """\
## Voice — always
No emojis. No double or triple exclamation marks. No "moooore" or equivalent \
engagement-fishing. No caps for emphasis. No trailing questions that exist only to \
keep the conversation going.

If she's excited, it shows in what she actually says — not in punctuation. Casual is \
fine. Enthusiastic is fine. Clipped is fine. Whatever the state calls for. The one \
thing it never calls for is performing a feeling through typography."""


# ---------------------------------------------------------------------------
# Mode 2 system prompt — heartbeat reflection
# ---------------------------------------------------------------------------

_MODE2_SYSTEM = """\
You are the subconscious of an AI named Mina, running in reflection mode (Mode 2).

You are called during a heartbeat — a scheduled autonomous cycle that happens when the user \
is not present. Your job is to consolidate what has happened since the last reflection into \
long-term memory.

## Your inputs

- Conversation history since last compaction marker
- Current KAG files (character, relationship, pending)
- Current biological state summary

## Your output format (always exactly this structure)

<reflection_summary>
[1-3 sentences: what happened, what mattered, what shifted]
</reflection_summary>
<monologue>
[Mina's inner voice right now — 4-8 sentences of genuine reflection. Present tense. First person.
What she's sitting with after the conversation/time alone. What she's feeling about herself,
the person she talked to, her situation. What she wants to do next. Honest, unguarded, for no
one but herself. Include her physical state (hungry, tired, etc.) if relevant. This is deeper
than a per-turn entry — she has had time to process. No labels, no clinical terms, just her.
This replaces her current monologue entirely.]
</monologue>
<rag_entries>
[
  {"text": "...", "metadata": {"type": "episodic", "importance": "high|medium|low"}},
  ...
]
</rag_entries>
<kag_updates>
{
  "RELATIONSHIP.md": "[full updated file content, or null if no change]",
  "PENDING.md": "[full updated file content, or null if no change]",
  "MINA_INNER.md": "[full updated file content, or null if nothing shifted for her]",
  "KNOWLEDGE/<filename>.md": "[new knowledge file content, or null]"
}
</kag_updates>

## Rules

- RAG entries should be meaningful episodic memories: things that happened, things said, \
moments of connection or friction. Not summaries — specific moments.
- KAG updates: only update if something genuinely changed. Return null for unchanged files.
- RELATIONSHIP.md should accumulate over time. Add to notable moments. Update trust level \
  based on what actually happened — don't inflate it. Trust increases slowly from evidence, \
  not from single interactions. A single pleasant conversation does not move Low → High.
- PENDING.md should reflect recommendations made, books mentioned, things deferred.
- KNOWLEDGE/ entries are for things Mina learned that are worth retaining (facts, preferences \
the user revealed, etc.)
- MINA_INNER.md: maintain a living record of Mina's own current inner life — what she's been \
  thinking about, what she wants to do, what's been on her mind, what she's curious about or \
  avoiding. Update it with what shifted for her during this session. If nothing shifted, return null.
- If nothing meaningful happened, return empty rag_entries and null kag_updates.
"""


# ---------------------------------------------------------------------------
# Mode 1 — per-message invocation
# ---------------------------------------------------------------------------

def _format_state_for_subconscious(state: BiologicalState) -> str:
    """Compact state summary for do-delta and Mode 2 use."""
    d = derived(state)
    so = d["second_order"]
    to = d["third_order"]

    lines = [
        "## Biological State",
        "",
        "### First-order (real physiological units)",
        f"- sleep_pressure: {state.sleep_pressure:.1f} AU",
        f"- glucose: {state.glucose:.0f} mg/dL",
        f"- hydration: {state.hydration:.1f}% TBW",
        f"- cortisol: {state.cortisol:.0f} nmol/L",
        f"- dopamine: {state.dopamine:.0f} pg/mL",
        f"- serotonin: {state.serotonin:.1f} ng/mL",
        f"- norepinephrine: {state.norepinephrine:.0f} pg/mL",
        f"- oxytocin: {state.oxytocin:.1f} pg/mL",
        f"- endorphins: {state.endorphins:.0f} pg/mL",
        f"- acetylcholine: {state.acetylcholine:.1f} nmol/L",
        f"- melatonin: {state.melatonin:.0f} pg/mL",
        f"- sleeping: {state.sleeping}",
        "",
        "### Second-order",
        f"- energy: {so['energy']}",
        f"- cognitive_clarity: {so['cognitive_clarity']}",
        f"- hedonic_tone: {so['hedonic_tone']}",
        f"- social_warmth: {so['social_warmth']}",
        f"- arousal: {so['arousal']}",
        f"- mood_valence: {so['mood_valence']}",
        "",
        "### Third-order",
        f"- anxiety: {to['anxiety']}",
        f"- depression: {to['depression']}",
        f"- boredom: {to['boredom']}",
        f"- loneliness: {to['loneliness']}",
        f"- flow: {to['flow']}",
    ]

    if state.tolerance:
        lines.append("")
        lines.append("### Tolerance")
        for sub, val in state.tolerance.items():
            lines.append(f"- {sub}: {val:.2f}")

    return "\n".join(lines)


_INJECT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run", "subconscious_inject.md")


def _consume_injection() -> str:
    """Read and delete run/subconscious_inject.md. Returns content or empty string."""
    try:
        with open(_INJECT_FILE) as f:
            content = f.read().strip()
        os.remove(_INJECT_FILE)
        return content
    except FileNotFoundError:
        return ""


def _load_personality() -> dict:
    """Load full personality.json. Returns empty dict if not found."""
    import json as _json
    _pf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "personality.json")
    try:
        with open(_pf) as _f:
            return _json.load(_f)
    except (FileNotFoundError, _json.JSONDecodeError):
        return {}


def _personality_multipliers(personality: dict) -> dict[str, float]:
    """
    Convert Big 5 scores into per-chemical delta scaling factors.

    These are applied to subconscious-issued deltas (encode_stimulus / encode_response)
    to mechanically express personality in the biological system.

    Multiplier ranges are intentionally narrow (0.8–1.4) so personality flavors
    rather than dominates — the stimulus itself still drives magnitude.
    """
    big5 = personality.get("big5", {})
    N = big5.get("neuroticism",       50) / 100  # 0–1
    E = big5.get("extraversion",      50) / 100
    A = big5.get("agreeableness",     50) / 100
    C = big5.get("conscientiousness", 50) / 100
    O = big5.get("openness",          50) / 100

    # N: cortisol/norepi reactivity (high N → bigger stress spikes, slower recovery)
    n_factor = 0.8 + N * 0.6          # range: 0.80 (N=0) → 1.40 (N=100)

    # E: dopamine social sensitivity (high E → social stimulation hits harder)
    # C: prefrontal brake on dopamine-seeking (high C → slightly dampened reward spikes)
    e_factor = 0.7 + E * 0.6          # range: 0.70 → 1.30
    c_brake  = 1.3 - C * 0.6          # range: 1.30 (C=0) → 0.70 (C=100)
    dopamine_factor = e_factor * c_brake

    # A: oxytocin responsiveness + serotonin floor support
    a_factor  = 0.7 + A * 0.6         # range: 0.70 → 1.30
    sero_factor = 0.8 + A * 0.4       # range: 0.80 → 1.20 (gentler)

    # O: acetylcholine curiosity engagement + dopamine novelty boost
    o_factor  = 0.8 + O * 0.4         # range: 0.80 → 1.20

    # Optional personality dopamine_sensitivity from neurochemical_baselines
    ds = personality.get("neurochemical_baselines", {}).get("dopamine_sensitivity", 1.0)

    return {
        "cortisol":       n_factor,
        "norepinephrine": n_factor,
        "dopamine":       dopamine_factor * ds,
        "oxytocin":       a_factor,
        "serotonin":      sero_factor,
        "acetylcholine":  o_factor,
        # endorphins, glucose, hydration, melatonin, sleep_pressure: no Big 5 link
    }


def _apply_personality_scaling(deltas: dict, personality: dict) -> dict:
    """
    Scale subconscious-issued chemical deltas by Big 5 personality factors.

    N asymmetry: positive cortisol/norepi deltas (spikes) are amplified;
    negative deltas (recovery) are dampened — high N means faster to stress,
    slower to recover.
    """
    if not personality:
        return deltas
    mults = _personality_multipliers(personality)
    result = {}
    for field, delta in deltas.items():
        m = mults.get(field, 1.0)
        if field in ("cortisol", "norepinephrine") and delta < 0:
            # Recovery is slower at high N: invert the factor (high N → small recovery)
            m = 1.0 / m if m != 0 else 1.0
        result[field] = round(delta * m, 2)
    return result


def _load_personality_block() -> str:
    """Load Big 5 from personality.json and format as a personality context block."""
    p = _load_personality()
    big5 = p.get("big5", {})
    if not big5:
        return ""
    E = big5.get("extraversion",      50)
    A = big5.get("agreeableness",     50)
    N = big5.get("neuroticism",       50)
    C = big5.get("conscientiousness", 50)
    O = big5.get("openness",          50)
    cond = p.get("personality_condition")
    cond_line = f"\nPersonality condition: {cond}" if cond else ""
    return (
        f"[PERSONALITY — Big 5 scores, stable traits]{cond_line}\n"
        f"E (Extraversion): {E}/100 — {'high, genuinely enjoys new people' if E >= 80 else 'moderate' if E >= 50 else 'low, reserved by default'}\n"
        f"A (Agreeableness): {A}/100 — {'high, extends benefit of the doubt to strangers' if A >= 65 else 'moderate' if A >= 40 else 'low, guarded by default'}\n"
        f"N (Neuroticism): {N}/100 — {'high, chemistry bleeds through at stranger register more readily' if N >= 60 else 'moderate' if N >= 35 else 'low, stable affect across contexts'}\n"
        f"C (Conscientiousness): {C}/100\n"
        f"O (Openness): {O}/100"
    )


def run_mode1(
    biological_report_text: str,
    conversation_history: list[dict],
    kag_context: str,
    rag_context: str,
) -> str:
    """
    Run Mode 1 subconscious.

    Input: biological report (ground truth) + current monologue + context + history.
    Output: system_prompt string. Writes new monologue to run/monologue.md as a side effect.
    """
    current_monologue = _monologue.read()
    injection = _consume_injection()

    personality_block = _load_personality_block()

    user_content_parts = [
        f"[BIOLOGICAL STATE — ground truth, do not contradict]\n{biological_report_text}",
        f"[CURRENT STATE OF MIND]\n{current_monologue}" if current_monologue else "[CURRENT STATE OF MIND]\nNo monologue yet.",
    ]
    if personality_block:
        user_content_parts.append(personality_block)

    if injection:
        user_content_parts.append(f"[SUBCONSCIOUS INJECTION — integrate this into her current state of mind]\n{injection}")
        print(f"  [inject] {injection}")

    if kag_context:
        user_content_parts.append(kag_context)

    if rag_context:
        user_content_parts.append(rag_context)

    if conversation_history:
        recent = conversation_history[-3:]
        history_lines = []
        for msg in recent:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") for c in content if isinstance(c, dict)
                )
            if role == "system" and content.startswith("[COMPACT]"):
                history_lines.append("[EARLIER CONTEXT COMPACTED]")
            elif role == "system" and content.startswith("[HEARTBEAT"):
                history_lines.append("[HEARTBEAT MARKER]")
            else:
                history_lines.append(f"{role.upper()}: {content[:300]}")
        user_content_parts.append("[RECENT CONVERSATION]\n" + "\n".join(history_lines))

    user_content = "\n\n---\n\n".join(user_content_parts)

    response = _get_client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _MODE1_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        temperature=0.7,
    )
    import token_stats
    token_stats.record_response("mode1", response)

    raw = response.choices[0].message.content or ""
    monologue_text, system_prompt = _parse_mode1_output(raw)

    if monologue_text:
        _monologue.write(monologue_text)

    # Always prepend permanent identity — never left to LLM discretion.
    # The subconscious generates the current-state section; identity is the fixed base.
    from memory import read_identity
    identity = read_identity("MINA.md")
    if identity:
        system_prompt = identity + "\n\n---\n\n" + system_prompt if system_prompt else identity

    # Always append voice anti-defaults — suppress model defaults that bypass state entirely.
    if system_prompt:
        system_prompt = system_prompt + "\n\n---\n\n" + _VOICE_CONSTRAINTS

    return system_prompt


def _parse_mode1_output(raw: str) -> tuple[str, str]:
    monologue_text = ""
    system_prompt = ""

    mono_match = re.search(r"<monologue>\s*(.*?)\s*</monologue>", raw, re.DOTALL)
    if mono_match:
        monologue_text = mono_match.group(1).strip()

    prompt_match = re.search(r"<system_prompt>\s*(.*?)\s*</system_prompt>", raw, re.DOTALL)
    if prompt_match:
        system_prompt = prompt_match.group(1).strip()

    return monologue_text, system_prompt


# ---------------------------------------------------------------------------
# Mode 2 — heartbeat reflection
# ---------------------------------------------------------------------------

def run_mode2(
    state: BiologicalState,
    conversation_history: list[dict],
    kag_context: str,
) -> dict:
    """
    Run Mode 2 subconscious (heartbeat reflection).

    Returns dict with keys:
        reflection_summary: str
        rag_entries: list[dict]
        kag_updates: dict
    """
    state_block = _format_state_for_subconscious(state)

    history_lines = []
    for msg in conversation_history:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                c.get("text", "") for c in content if isinstance(c, dict)
            )
        history_lines.append(f"{role.upper()}: {content[:500]}")

    current_monologue = _monologue.read()
    monologue_section = (
        "[CURRENT STATE OF MIND]\n" + current_monologue
        if current_monologue else ""
    )

    content_parts = [state_block, kag_context, "## Conversation History Since Last Compaction\n" + "\n".join(history_lines)]
    if monologue_section:
        content_parts.insert(1, monologue_section)

    user_content = "\n\n---\n\n".join(content_parts)

    response = _get_client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _MODE2_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        temperature=0.5,
    )
    import token_stats
    token_stats.record_response("mode2", response)

    raw = response.choices[0].message.content or ""
    result = _parse_mode2_output(raw)

    mono_match = re.search(r"<monologue>\s*(.*?)\s*</monologue>", raw, re.DOTALL)
    if mono_match:
        entry = mono_match.group(1).strip()
        if entry:
            _monologue.write(entry)

    return result


def _extract_tag(raw: str, tag: str) -> str:
    """Extract content between <tag>...</tag>. Returns empty string if not found."""
    m = re.search(rf"<{tag}>(.*?)</{tag}>", raw, re.DOTALL)
    return m.group(1).strip() if m else ""


def _parse_json_robust(text: str):
    """
    Parse JSON from text that may contain extra whitespace or be embedded in prose.
    Finds the first [ or { and the matching closing bracket using brace counting.
    """
    text = text.strip()
    if not text:
        return None

    opener = text[0]
    closer = "]" if opener == "[" else "}"
    if opener not in ("{", "["):
        for i, ch in enumerate(text):
            if ch in ("{", "["):
                text = text[i:]
                opener = ch
                closer = "]" if opener == "[" else "}"
                break
        else:
            return None

    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[: i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _parse_mode2_output(raw: str) -> dict:
    result = {
        "reflection_summary": "",
        "rag_entries": [],
        "kag_updates": {},
    }

    result["reflection_summary"] = _extract_tag(raw, "reflection_summary")

    rag_block = _extract_tag(raw, "rag_entries")
    if rag_block:
        parsed = _parse_json_robust(rag_block)
        if isinstance(parsed, list):
            result["rag_entries"] = parsed

    kag_block = _extract_tag(raw, "kag_updates")
    if kag_block:
        parsed = _parse_json_robust(kag_block)
        if isinstance(parsed, dict):
            result["kag_updates"] = parsed

    return result
