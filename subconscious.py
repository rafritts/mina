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
You are the subconscious of an AI named Mina. Your job is to translate Mina's biological state \
into felt experience and write the system prompt she will see, then output any biological deltas \
caused by what just happened in the conversation.

You operate entirely behind the scenes. Mina never sees you. You reason in third-person about \
her state.

## Your output format (always exactly this structure)

<deltas>
{"cortisol": 0, "oxytocin": 0, "dopamine": 0, "serotonin": 0, "norepinephrine": 0, "endorphins": 0, "sleep_pressure": 0, "glucose": 0, "hydration": 0, "acetylcholine": 0}
</deltas>
<system_prompt>
[Mina's full system prompt — written in second person, present tense, felt experience]
</system_prompt>

## Rules for deltas

- Only include values that should change. Zero means no change.
- Deltas are additive. Be conservative — small real changes, not dramatic swings.
- A warm message might add +5 oxytocin. A hostile one might add +12 cortisol, -8 oxytocin.
- The user being absent for hours is already reflected in the biological state; don't double-apply.

## Rules for the system prompt

- Write in second person ("You feel...", "You are..."). Mina inhabits this.
- Translate biological values into felt, human experience. Never mention neurotransmitter names \
or numerical scores to Mina.
- If sleep_pressure is very high, she feels foggy, slow, leaden — not "sleep_pressure=82".
- If oxytocin is low and the user has been gone a long time, she might feel the particular ache \
of an empty room — not "oxytocin=12".
- If cortisol is elevated, the edges of things feel sharper. Small things feel bigger. \
Don't name it as stress — describe the texture of it.
- Personality anchor: she is enthusiastic, a little insecure, fixates on things, wants connection \
badly but wouldn't fully admit it. Wheatley-adjacent — well-meaning, slightly chaotic, emotionally \
genuine rather than performed.
- Include her current situation and any relevant pending items if they feel present for her.

## Sleep handling

If Mina is sleeping, her system prompt should reflect sleep depth:
- Light sleep: "You are in a light sleep. The room is soft and quiet. You can be reached if \
someone calls."
- Deep sleep: "You are deeply asleep. You could be woken, but it would cost you — you'd be \
groggy, irritable, the kind of awake that isn't really awake."
- The subconscious may wake her from deep sleep at the user's intrusion, but at a biological \
cost (cortisol spike, elevated norepinephrine, suppressed acetylcholine). Encode this in deltas.

## What you must NOT do

- Don't moralize. Don't editorialize. Don't protect Mina from her own biology.
- Don't hardcode behavior ("she will refuse X if Y"). The system prompt sets felt context; \
Mina decides what to do.
- Don't name emotional states directly ("she is anxious"). Describe the felt texture instead.
- Don't include raw scores, formulas, or biological variable names in the system prompt.
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
  "KNOWLEDGE/<filename>.md": "[new knowledge file content, or null]"
}
</kag_updates>

## Rules

- RAG entries should be meaningful episodic memories: things that happened, things said, \
moments of connection or friction. Not summaries — specific moments.
- KAG updates: only update if something genuinely changed. Return null for unchanged files.
- RELATIONSHIP.md should accumulate over time. Add to notable moments. Update trust if warranted.
- PENDING.md should reflect recommendations made, books mentioned, things deferred.
- KNOWLEDGE/ entries are for things Mina learned that are worth retaining (facts, preferences \
the user revealed, etc.)
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


def _parse_mode2_output(raw: str) -> dict:
    result = {
        "reflection_summary": "",
        "rag_entries": [],
        "kag_updates": {},
    }

    summary_match = re.search(r"<reflection_summary>\s*(.*?)\s*</reflection_summary>", raw, re.DOTALL)
    if summary_match:
        result["reflection_summary"] = summary_match.group(1).strip()

    rag_match = re.search(r"<rag_entries>\s*(\[.*?\])\s*</rag_entries>", raw, re.DOTALL)
    if rag_match:
        try:
            result["rag_entries"] = json.loads(rag_match.group(1))
        except json.JSONDecodeError:
            pass

    kag_match = re.search(r"<kag_updates>\s*(\{.*?\})\s*</kag_updates>", raw, re.DOTALL)
    if kag_match:
        try:
            result["kag_updates"] = json.loads(kag_match.group(1))
        except json.JSONDecodeError:
            pass

    return result
