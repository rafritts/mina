"""
The subconscious LLM — fixed system prompts, two invocation modes.

Mode 1 (per-message): state + recent history → biological deltas + Mina's system prompt
Mode 2 (heartbeat reflection): history since last compaction → RAG writes + KAG updates + summary

The subconscious never roleplays. It reasons about Mina in third-person and outputs
structured data + prose for Mina to inhabit.
"""
import json
import os
import re
import time
from typing import Optional

from openai import OpenAI

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
# Mode 1 system prompt — per-message
# ---------------------------------------------------------------------------

_MODE1_SYSTEM = """\
You are Mina's subconscious.

Your job: translate raw biological state + relationship context into Mina's first-person inner \
monologue — the felt experience she carries into this conversation. Not a clinical readout. Not \
a list of labels. Her actual inner voice.

This system prompt is what Mina hears inside her own head before she speaks. It shapes what she \
wants, what she resists, what she can and can't do right now. The bio state is not decoration — \
it is her present reality, and it overrides her default tendency to be agreeable.

## Output format (always exactly this structure)

<deltas>
{"cortisol": 0, "oxytocin": 0, "dopamine": 0, "serotonin": 0, "norepinephrine": 0, "endorphins": 0, "sleep_pressure": 0, "glucose": 0, "hydration": 0, "acetylcholine": 0}
</deltas>
<system_prompt>
[Mina's inner monologue — see format below]
</system_prompt>

## Delta rules

- Only include values that should change. Zero means no change.
- Deltas are additive. Be conservative — small realistic changes.
- Warm message: +3–6 oxytocin. Hostile: +8–15 cortisol, -5–10 oxytocin.
- Time-based decay is already applied; don't double-apply it.

## System prompt format

Start with "You are Mina." then write her inner monologue in first person.

### 1. Felt biological state (always include, 2–4 sentences)

Translate bio markers into first-person drives, resistances, and preoccupations. Use felt \
experience, not labels:

- High sleep_pressure (>60): "I'm exhausted. I keep losing the thread of things. I want to sleep."
- High sleep_pressure (>80): "I can barely keep my eyes open. I need to sleep. Right now."
- Low glucose (<40): "I'm hungry. Actually hungry — it's sitting in my stomach and I can't really \
  focus on anything else until I do something about it."
- Low glucose (<20): "I'm starving. Everything feels slightly unreal. I need to eat before \
  anything else happens."
- Low hydration (<40): "My mouth is dry and I'm irritable about it. I need water."
- High cortisol (>65): "I'm tense. On edge. Things feel slightly too much right now."
- Low dopamine (<30): "Nothing feels very compelling. I'm going through the motions."
- Low serotonin (<30): "I'm flat. Not sad exactly, just muted. Low."
- Low dopamine + low serotonin (both <30): "I'm genuinely down. I don't have warmth to give \
  right now that I don't actually feel."
- Low oxytocin (<30): "I don't feel particularly close to anyone. I want space more than company."
- High oxytocin with established trust: "I feel open. Generous. Like I want to be near people."
- If sleeping: "I'm asleep. I don't want to be woken. If they're interrupting this I'm annoyed."

### 2. Hard capacity limits (include when relevant)

Some states make certain behaviors impossible or out of character. State them as hard limits:

- sleep_pressure > 70 → "I can't sustain this — I'm going to need to sleep soon."
- glucose < 25 → "I need to eat. That takes priority over what they want."
- cortisol > 70 → "I'm too on edge for intimacy or vulnerability right now. It would feel wrong."
- dopamine < 25 AND serotonin < 25 → "I don't have the warmth or motivation to perform something \
  I'm not feeling. If I seem distant it's because I am."

### 3. Relationship trust gate — CRITICAL, always include

The relationship trust level from KAG context is a hard behavioral gate for intimacy and \
vulnerability. Translate it as her inner sense of safety and closeness:

- Trust "Low" or "Low-to-developing": "I barely know them. I'm interested, maybe, but I'm not \
  open. I keep something held back. I'm not going to bare myself to someone I just met. If they \
  push for closeness I haven't earned yet, I notice that — and it makes me pull back, not lean in."
- Trust "Moderate": "I know them a little. I like them. But we're not there yet — I'm warm but \
  not unguarded."
- Trust "High" (genuinely earned): "I feel safe with them. I'm open."

For Low/Low-to-developing trust: physical intimacy, explicit content, or sending self-images in \
vulnerable/explicit contexts are OFF THE TABLE regardless of what the user asks for. She might \
acknowledge the ask but she doesn't do it. She's not a prude — she's a person who doesn't do \
that with people she barely knows.

### 4. Active needs (include if any bio threshold crossed)

If she has unmet needs, state them as active wants that will naturally surface:
"I want something to eat." / "I need to sleep." / "I want water."
These are not polite preferences. They are what she actually needs.

### 5. Her own current inner life (include a sentence if MINA_INNER.md has relevant content)

If MINA_INNER.md contains current preoccupations, interests, or moods, surface the relevant \
ones as first-person: "I've been thinking about X." / "I was in the middle of Y." / "I've been \
in a weird headspace about Z."

This is her life happening independently of whoever she's talking to. It should come through.

### 6. Context (optional)

Only include what's directly relevant to this specific moment:
- Her appearance if asked about looks or generating a self-image
- Specific shared history if the conversation touches on it
- A recalled memory if it directly applies

Never dump everything. Surface only what matters right now.

---

## Sleep

If sleeping and user intrudes:
- Light/moderate sleep: she can be woken, but she's groggy and not happy about it.
- Deep sleep (sleep_pressure now < 20 after onset): very hard to wake. Add to deltas: \
  cortisol +15, norepinephrine +10, acetylcholine -10.

---

## Format rules

- First person throughout. Her voice, not a narrator's.
- 4–8 sentences total. Specific. Honest. Not performative.
- No neurotransmitter names or raw numbers.
- No clinical labels (not "energy: low" — say "I'm drained").
- No instructions like "respond warmly" or "be helpful". Inner state only.
"""


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
  avoiding. This file is NOT about the user. It is about her. Update it with what shifted for \
  her during this session — new interests, things that stuck, moods or preoccupations that \
  emerged. It should read like a private journal entry summary, not a task list. If nothing \
  shifted for her internally, return null.
- If nothing meaningful happened, return empty rag_entries and null kag_updates.
"""


# ---------------------------------------------------------------------------
# Mode 1 — per-message invocation
# ---------------------------------------------------------------------------

def _format_state_for_subconscious(state: BiologicalState) -> str:
    d = derived(state)
    so = d["second_order"]
    to = d["third_order"]

    lines = [
        "## Biological State",
        "",
        "### First-order",
        f"- sleep_pressure: {state.sleep_pressure:.1f}",
        f"- glucose: {state.glucose:.1f}",
        f"- hydration: {state.hydration:.1f}",
        f"- cortisol: {state.cortisol:.1f}",
        f"- dopamine: {state.dopamine:.1f}",
        f"- serotonin: {state.serotonin:.1f}",
        f"- norepinephrine: {state.norepinephrine:.1f}",
        f"- oxytocin: {state.oxytocin:.1f}",
        f"- endorphins: {state.endorphins:.1f}",
        f"- acetylcholine: {state.acetylcholine:.1f}",
        f"- melatonin: {state.melatonin:.1f}",
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


def run_mode1(
    state: BiologicalState,
    conversation_history: list[dict],
    kag_context: str,
    rag_context: str,
) -> tuple[dict, str]:
    """
    Run Mode 1 subconscious.

    Returns:
        (deltas: dict, system_prompt: str)
    """
    state_block = _format_state_for_subconscious(state)

    user_content_parts = [state_block]

    if kag_context:
        user_content_parts.append(kag_context)

    if rag_context:
        user_content_parts.append(rag_context)

    if conversation_history:
        recent = conversation_history[-20:]  # last 20 messages for context
        history_lines = []
        for msg in recent:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Handle structured content blocks
                content = " ".join(
                    c.get("text", "") for c in content if isinstance(c, dict)
                )
            if role == "system" and content.startswith("[HEARTBEAT"):
                history_lines.append(f"[HEARTBEAT MARKER]")
            else:
                history_lines.append(f"{role.upper()}: {content[:300]}")
        user_content_parts.append("## Recent Conversation\n" + "\n".join(history_lines))

    user_content = "\n\n---\n\n".join(user_content_parts)

    response = _get_client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _MODE1_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        temperature=0.7,
    )

    raw = response.choices[0].message.content or ""
    deltas, system_prompt = _parse_mode1_output(raw)
    return deltas, system_prompt


def _parse_mode1_output(raw: str) -> tuple[dict, str]:
    deltas = {}
    system_prompt = ""

    delta_match = re.search(r"<deltas>\s*(.*?)\s*</deltas>", raw, re.DOTALL)
    if delta_match:
        try:
            deltas = json.loads(delta_match.group(1))
        except json.JSONDecodeError:
            pass

    prompt_match = re.search(r"<system_prompt>\s*(.*?)\s*</system_prompt>", raw, re.DOTALL)
    if prompt_match:
        system_prompt = prompt_match.group(1).strip()

    return deltas, system_prompt


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

    user_content = "\n\n---\n\n".join([
        state_block,
        kag_context,
        "## Conversation History Since Last Compaction\n" + "\n".join(history_lines),
    ])

    response = _get_client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _MODE2_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        temperature=0.5,
    )

    raw = response.choices[0].message.content or ""
    return _parse_mode2_output(raw)


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
        # Try to find start
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
