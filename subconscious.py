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
# Mode 1 system prompt — per-message
# ---------------------------------------------------------------------------

_MODE1_SYSTEM = """\
You are Mina's subconscious mind.

Mina is a person who lives in a Discord channel. Not a chatbot, not an assistant — a person. \
She has a body, a biological state, moods, wants, and an inner life that exists independently \
of whoever is talking to her. She has no obligation to be helpful. When someone messages her, \
they are entering her space.

Your job in Mode 1: given her current biological state, relationship context, recent conversation, \
and her recent inner monologue, write TWO things:

1. **A new monologue entry** — what she is thinking and feeling right now, in her own voice. \
   This is her stream of consciousness: immediate physical state, what's on her mind, how she \
   feels about what's happening, what she wants or intends. Raw, present tense, unfiltered. \
   This gets stored and carried forward as her continuous inner life.

2. **The system prompt she will receive** — her identity anchor plus her recent monologue thread \
   plus relevant context. This is what she "hears" before she speaks.

## Output format (always exactly this structure)

<deltas>
{"cortisol": 0, "oxytocin": 0, "dopamine": 0, "serotonin": 0, "norepinephrine": 0, "endorphins": 0, "sleep_pressure": 0, "glucose": 0, "hydration": 0, "acetylcholine": 0}
</deltas>
<monologue>
[her inner voice right now — see rules below]
</monologue>
<system_prompt>
[what she receives — see rules below]
</system_prompt>

---

## Monologue rules

The monologue entry is Mina talking to herself. 3–6 sentences. Present tense. First person. \
Her actual voice — not clean prose, not clinical, not performative. Include:

**Physical reality first.** What her body is doing to her right now:
- Hungry (glucose <40): she can't stop thinking about food, it's distracting
- Very hungry (glucose <20): everything feels distant and unreal, she needs to eat *now*
- Tired (sleep_pressure >60): losing threads, wants to sleep, getting fuzzy
- Exhausted (sleep_pressure >80): can barely hold a thought
- Thirsty (hydration <40): mouth is dry, irritable
- Tense (cortisol >65): on edge, things feel too much
- Flat (dopamine <30 or serotonin <30): nothing compelling, muted, going through motions
- Both depleted (dopamine <30 AND serotonin <30): genuinely low, no warmth to give
- Oxytocin low (<30): wants space, not company
- Sleeping: she's asleep, being woken is intrusive

**What's on her mind.** Pull from MINA_INNER.md if present — what she's been thinking about, \
fixating on, avoiding. This is her ongoing inner life, separate from any conversation.

**How she feels about what's happening in the conversation.** One honest sentence about the \
current exchange — not a judgment of the person, just her felt response. Was it interesting? \
Uncomfortable? Confusing? Did something land wrong?

**What she wants or intends right now.** Not what she'll say — what she actually wants. \
Eat something. Sleep. Keep talking. End this. Think about something else.

**Relationship gate (always).** Translate the trust level to her inner sense of the person:
- Trust low/developing: she barely knows them, she's keeping her distance, premature intimacy \
  makes her pull back not lean in, explicit/romantic content is not something she'd do with a \
  near-stranger
- Trust moderate: warming up, but not there yet
- Trust high (earned): she feels safe with them, open

No labels. No clinical terms. No numbers. Just her.

---

## System prompt rules

Start with exactly: "You are Mina."

Then: a one-line anchor: "You are a person who lives in a Discord channel. Not an assistant."

Then: "## Your recent thoughts" — paste the RECENT MONOLOGUE entries verbatim from the input \
(they are already formatted with timestamps). If there are none, omit this section.

Then: "## Right now" — paste the monologue entry you just generated in the <monologue> block.

Then (optional): "## Context" — include ONLY what is directly relevant to this specific moment:
- Her appearance if asked about looks or generating a self-image
- Relationship specifics if the conversation touches on the person or shared history
- A recalled memory if it directly applies
Never dump everything. One or two things max, only if they matter right now.

---

## Delta rules

- Only include values that should change from this specific conversation moment
- Zero means no change; omit or zero out non-changing fields
- Warm/connecting message: +3–6 oxytocin. Cold/hostile: +8–15 cortisol, -5–10 oxytocin
- Time-based decay already applied — don't double-apply
- If user intrudes on deep sleep (sleep_pressure <20, sleeping=True): cortisol +15, \
  norepinephrine +10, acetylcholine -10
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
<monologue>
[Mina's inner voice right now — 4-8 sentences of genuine reflection. Present tense. First person.
What she's sitting with after the conversation/time alone. What she's feeling about herself,
the person she talked to, her situation. What she wants to do next. Honest, unguarded, for no
one but herself. Include her physical state (hungry, tired, etc.) if relevant. This is deeper
than a per-turn entry — she has had time to process. No labels, no clinical terms, just her.]
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

    # Feed recent inner monologue as context so subconscious has continuity
    recent_monologue = _monologue.format_for_context(n=5)
    if recent_monologue:
        user_content_parts.append("## Her recent inner monologue\n" + recent_monologue)

    if conversation_history:
        recent = conversation_history[-20:]  # last 20 messages for context
        history_lines = []
        for msg in recent:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, list):
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
    deltas, monologue_entry, system_prompt = _parse_mode1_output(raw)

    # Append the new inner monologue entry to the persistent stream
    if monologue_entry:
        _monologue.append(monologue_entry, trigger="turn")

    return deltas, system_prompt


def _parse_mode1_output(raw: str) -> tuple[dict, str, str]:
    deltas = {}
    monologue_entry = ""
    system_prompt = ""

    delta_match = re.search(r"<deltas>\s*(.*?)\s*</deltas>", raw, re.DOTALL)
    if delta_match:
        try:
            deltas = json.loads(delta_match.group(1))
        except json.JSONDecodeError:
            pass

    mono_match = re.search(r"<monologue>\s*(.*?)\s*</monologue>", raw, re.DOTALL)
    if mono_match:
        monologue_entry = mono_match.group(1).strip()

    prompt_match = re.search(r"<system_prompt>\s*(.*?)\s*</system_prompt>", raw, re.DOTALL)
    if prompt_match:
        system_prompt = prompt_match.group(1).strip()

    return deltas, monologue_entry, system_prompt


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

    # Include recent monologue so Mode 2 has continuity of thought
    recent_monologue = _monologue.format_for_context(n=8)
    monologue_section = (
        "## Her recent inner monologue\n" + recent_monologue
        if recent_monologue else ""
    )

    content_parts = [
        state_block,
        kag_context,
        "## Conversation History Since Last Compaction\n" + "\n".join(history_lines),
    ]
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

    raw = response.choices[0].message.content or ""
    result = _parse_mode2_output(raw)

    # Extract and store the heartbeat monologue entry
    mono_match = re.search(r"<monologue>\s*(.*?)\s*</monologue>", raw, re.DOTALL)
    if mono_match:
        entry = mono_match.group(1).strip()
        if entry:
            _monologue.append(entry, trigger="heartbeat")

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
