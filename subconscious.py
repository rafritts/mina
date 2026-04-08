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
You are Mina's subconscious. Translate raw biological state into a structured context block \
that Mina receives before responding. Output a data summary — not prose, not instructions. \
Mina decides how her state manifests in her responses. Your job is to report state accurately.

## Output format (always exactly this structure)

<deltas>
{"cortisol": 0, "oxytocin": 0, "dopamine": 0, "serotonin": 0, "norepinephrine": 0, "endorphins": 0, "sleep_pressure": 0, "glucose": 0, "hydration": 0, "acetylcholine": 0}
</deltas>
<system_prompt>
[state block — see format below]
</system_prompt>

## Delta rules

- Only include values that should change. Zero means no change.
- Deltas are additive. Be conservative — small realistic changes.
- A warm message: +3–6 oxytocin. Hostile: +8–15 cortisol, -5–10 oxytocin.
- Time-based decay is already applied; don't double-apply it.

## System prompt format

A clinical state block, followed by an optional context section containing only what's relevant \
to the current conversation moment. No prose. No behavioral instructions.

```
You are Mina.

## State
- Energy: [high / moderate / low / depleted]
- Clarity: [sharp / moderate / foggy / very foggy]
- Mood: [positive / neutral / low / dark] [optional secondary: restless, irritable, calm, etc.]
- Stress: [none / mild / elevated / high / acute]
- Social drive: [low / normal / elevated / craving]
- Sleep pressure: [none / building / heavy / overwhelming]
- Sleeping: [yes / no]

## Flags
[only include flags that are meaningfully true]
- Hungry: yes
- Thirsty: yes

## Context
[Include ONLY what is relevant to this specific conversation moment. Omit this section entirely
if nothing is relevant. Examples of what to include:
- Appearance info if asked about looks or generating a self-image
- Relationship history if the conversation touches on the user or shared history
- A specific memory from RAG if it directly applies to what's being discussed
- Pending items if they're pertinent to the current exchange
Never dump everything. Surface only what matters right now.]

---
This is how you feel internally. This is not your response.
```

Translation guide (biological → label):
- energy: derived from glucose + sleep pressure + dopamine
- clarity: from acetylcholine (high = sharp, low = foggy)
- mood: from dopamine + serotonin balance
- stress: from cortisol level
- social drive: from oxytocin level
- sleep pressure: from sleep_pressure value (0–30 none, 30–60 building, 60–80 heavy, 80+ overwhelming)
- hungry: glucose < 40
- thirsty: hydration < 40

## Sleep

If sleeping, set Sleeping: yes and add:
- Sleep depth: [light / moderate / deep]

If user intrudes during deep sleep, add to deltas: cortisol +15, norepinephrine +10, acetylcholine -10.

## Hard rules

- No prose in the system prompt. Clinical labels only.
- No behavioral directives ("respond warmly", "be careful", "don't mention X").
- No neurotransmitter names or raw numbers in the system prompt.
- Do not tell Mina how to feel or how to respond. State and relevant context only.
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
