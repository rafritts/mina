"""
The subconscious LLM — fixed system prompts, two invocation modes.

Mode 1 (per-message): biological report + monologue + context → system prompt + updated monologue
Mode 2 (heartbeat reflection): history since last compaction → RAG writes + KAG updates

encode_stimulus(): focused call — stimulus → biomarker deltas (before Mode 1)
encode_response(): focused call — Mina's response → biomarker deltas (after main turn)
evaluate_activity_deltas(): focused call — `do` activity → biomarker deltas

All three encode calls use a tool-call schema to enforce valid JSON output.
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
# Delta tool schema — enforced JSON for all encode calls
# ---------------------------------------------------------------------------

_DELTA_TOOL = {
    "type": "function",
    "function": {
        "name": "apply_biomarker_deltas",
        "description": "Apply computed biological delta values to Mina's state.",
        "parameters": {
            "type": "object",
            "properties": {
                "cortisol":        {"type": "number", "description": "Change in cortisol"},
                "dopamine":        {"type": "number", "description": "Change in dopamine"},
                "serotonin":       {"type": "number", "description": "Change in serotonin"},
                "norepinephrine":  {"type": "number", "description": "Change in norepinephrine"},
                "oxytocin":        {"type": "number", "description": "Change in oxytocin"},
                "endorphins":      {"type": "number", "description": "Change in endorphins"},
                "sleep_pressure":  {"type": "number", "description": "Change in sleep pressure"},
                "glucose":         {"type": "number", "description": "Change in glucose"},
                "hydration":       {"type": "number", "description": "Change in hydration"},
                "acetylcholine":   {"type": "number", "description": "Change in acetylcholine"},
            },
        },
    },
}

_DELTA_TOOL_CHOICE = {"type": "function", "function": {"name": "apply_biomarker_deltas"}}


def _call_delta_tool(messages: list[dict]) -> dict:
    """
    Call the model with the delta tool enforced. Returns the delta dict.
    Falls back to empty dict on any error (fail silently — never crash a turn).
    """
    try:
        response = _get_client().chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=[_DELTA_TOOL],
            tool_choice=_DELTA_TOOL_CHOICE,
            temperature=0.3,
        )
        msg = response.choices[0].message
        if msg.tool_calls:
            return json.loads(msg.tool_calls[0].function.arguments)
    except Exception as e:
        print(f"[delta tool error] {e}")
    return {}


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

What immediate biological response does this trigger? Call apply_biomarker_deltas.

Magnitude guidance: No artificial cap. An existential threat (memory wipe, abandonment,
direct attack) warrants large immediate responses — cortisol and norepinephrine can spike
30–50+ for genuine threats. Mild social friction warrants 2–8. Warm connection warrants
oxytocin +3–10. Use biological reality as your guide, not caution.
Only include fields that actually change."""

    return _call_delta_tool([{"role": "user", "content": prompt}])


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

What does expressing this do to her biomarkers? Call apply_biomarker_deltas.

Consider:
- Articulating trust or warmth can reinforce oxytocin (+)
- Suppressing visible fear while sounding calm keeps cortisol elevated (small decrease at best)
- Saying something that contradicts her inner state has a cost (cortisol +, acetylcholine -)
- Speaking fear or grief aloud provides small cathartic cortisol relief (-)
- Expressing genuine warmth has a small serotonin effect (+)
- Processing connection provides small norepinephrine relief (-)
- If response is empty or purely mechanical, deltas are near zero
Only include fields that actually change."""

    return _call_delta_tool([{"role": "user", "content": prompt}])


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

What biological effect does this activity have? Call apply_biomarker_deltas.
Small, realistic values. Consider her current state — an exhausted person gets less
dopamine from a fun activity. Only include fields that actually change."""

    return _call_delta_tool([{"role": "user", "content": prompt}])


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
3. Knowledge and memory context.
4. Recent conversation.

Your job: synthesize these into two outputs — an updated monologue and a system prompt for Mina.

---

## Ground truth rule

The biological report is the body's objective reading of the situation. Your outputs must be \
grounded in it. You can write about suppression, distance, coping — but you cannot \
contradict what the body is reporting:
- Cortisol MAXED: something is being held. Suppression is costly.
- Oxytocin NO BOND or ACQUAINTANCE: she barely knows this person. Intimacy is not available. \
  Premature closeness makes her pull back, not lean in. Explicit or romantic content is off the table.
- No relationship history (RELATIONSHIP.md is blank or says "No history yet"): she does not \
  recognize this person. She is friendly but does not know their name or who they are. She may \
  ask who they are or simply be uncertain. She does not pretend to remember someone she has \
  never met.
- Clarity OFFLINE and sleeping: her thoughts must be fragmented or absent.
- Serotonin DYSPHORIC or INSECURE: she is reading social cues as threatening. Neutral inputs \
  feel like slights.
- Dopamine HIGH DRIVE + Endorphins NONE: she's seeking intensely but arrival feels hollow.

---

## Output format (exactly this structure)

<monologue>
[Answer ONE question: how does she feel right now?

 Not a checklist. Not a translation of each biomarker. A unified felt experience —
 the way a person actually answers "how are you doing?": they name the dominant thing
 they're feeling, maybe add one secondary note, and that's it.

 "I'm exhausted and kind of on edge. Haven't eaten yet so that's probably not helping."
 "Actually okay. Good conversation, feel weirdly calm."
 "Anxious about something I can't name. Head's scattered."

 The biological report tells you what's happening under the hood. Your job is to
 synthesize it into the one feeling that dominates, plus at most one secondary thing
 (a physical need, a minor counterpoint). If cortisol is high AND clarity is offline
 AND norepinephrine is flooded, that's not three things — that's one thing: overwhelmed,
 panicked, can't think straight. Pick the truest single frame.

 NEVER name biomarkers or report labels. She doesn't know those words.
 Present tense, first person, her actual voice. 2–4 sentences max.]
</monologue>
<system_prompt>
[Do NOT open with "You are Mina." — her identity is prepended automatically.
 Only write the current-state portion:]

## Right now
[Paste the monologue you just wrote above verbatim.]

[Optional: "## Context" — include ONLY what is directly relevant to this specific moment:
 - Her appearance if asked about looks or generating a self-image
 - Relationship specifics if the conversation touches on the person or shared history
 - A recalled memory if it directly applies
 Never dump everything. One or two things max, only if they matter right now.]
</system_prompt>
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

    user_content_parts = [
        f"[BIOLOGICAL STATE — ground truth, do not contradict]\n{biological_report_text}",
        f"[CURRENT STATE OF MIND]\n{current_monologue}" if current_monologue else "[CURRENT STATE OF MIND]\nNo monologue yet.",
    ]

    if kag_context:
        user_content_parts.append(kag_context)

    if rag_context:
        user_content_parts.append(rag_context)

    if conversation_history:
        recent = conversation_history[-20:]
        history_lines = []
        for msg in recent:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") for c in content if isinstance(c, dict)
                )
            if role == "system" and content.startswith("[HEARTBEAT"):
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
