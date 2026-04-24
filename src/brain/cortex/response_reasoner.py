"""
Conversation Pillar — Response Reasoner (SPEC-51).

Runs between stimulus encoding and response generation. Deliberates on how Mina
should handle the incoming message: raw first-person reaction first, then strategy.

Output is structured JSON. cortex.py owns serialization into the system prompt.
"""
import json
import os
import re
import time

from src.application.infra.client import chat_create, MODEL
from src.application.infra import token_stats
from src.application.infra.log import log
from src.brain.brainstem.state import BiologicalState, derived
from src.config.config import RUN_DIR

_QUESTION_QUEUE_FILE = os.path.join(RUN_DIR, "question_queue.json")
_FOLLOW_UP_THOUGHTS_FILE = os.path.join(RUN_DIR, "follow_up_thoughts.json")

VALID_APPROACHES = frozenset({
    "banter", "sincere", "question", "deflect",
    "ignore", "vulnerable", "warm", "brief",
})

_REQUIRED_FIELDS = (
    "internal_reaction", "approach", "tone", "lead_with",
    "subtext_detected", "lean_into_subtext", "strategy_rationale",
    "follow_up_thoughts", "follow_up_questions",
)

_SYSTEM = """\
You are doing Mina's internal reasoning — a character in an ongoing simulation.
You are NOT writing her response. You are deciding how she actually feels about this message,
and then what she is going to do about it.

Two steps. First, her raw reaction — unfiltered, honest, in her voice.
Not what she'll say. What she actually thinks when she reads it.
"idle chitchat again. I'm tired." or "oh that's actually interesting."

Second, her strategy — given that reaction, how does she handle it?
These are coupled. A bad reaction doesn't mean a cold response. A warm reaction doesn't mean she shows it.

Return only a JSON object. No markdown, no fences, no extra commentary.

Required fields:
  "internal_reaction"   — raw first-person thought, her voice, lowercase, unpolished
  "approach"            — one of: banter, sincere, question, deflect, ignore, vulnerable, warm, brief
  "tone"                — one-line tone descriptor
  "lead_with"           — what to open with: a question, observation, or reaction
  "subtext_detected"    — any innuendo, leading question, or unstated thing (or null)
  "lean_into_subtext"   — true or false
  "strategy_rationale"  — why this approach; can reference the reaction
  "follow_up_thoughts"  — list of things she keeps thinking about after (may be empty)
  "follow_up_questions" — list of questions she wants to ask when the moment is right (may be empty)"""


def _compute_normalized(state: BiologicalState, name: str) -> float:
    from src.brain.subconscious.decoder import _NORM_SCALE, _get_chem_val
    floor, ceiling = _NORM_SCALE.get(name, (0.0, 1.0))
    span = ceiling - floor
    if span <= 0:
        return 0.0
    val = _get_chem_val(state, name)
    return max(0.0, (val - floor) / span * 10.0)


def _state_summary(state: BiologicalState) -> str:
    """Brief state summary for injection into the reasoning prompt."""
    d = derived(state)
    so = d["second_order"]
    to = d["third_order"]

    monoamines = ["dopamine", "serotonin", "norepinephrine", "cortisol",
                  "oxytocin", "gaba", "endorphins", "anandamide"]
    norms = {name: _compute_normalized(state, name) for name in monoamines}
    dominant = max(norms, key=lambda k: norms[k])

    mood = so["mood_valence"] / 100.0
    energy = so["energy"] / 100.0
    anxiety = to["anxiety"] / 100.0

    return (
        f"dominant signal: {dominant} ({norms[dominant]:.1f}/10). "
        f"dopamine {norms['dopamine']:.1f}, serotonin {norms['serotonin']:.1f}, "
        f"cortisol {norms['cortisol']:.1f}, oxytocin {norms['oxytocin']:.1f}. "
        f"mood {mood:.2f}, energy {energy:.2f}, anxiety {anxiety:.2f}."
    )


def _load_question_queue() -> list[str]:
    try:
        with open(_QUESTION_QUEUE_FILE) as f:
            data = json.load(f)
        if isinstance(data, list):
            return [q for q in data if isinstance(q, str)]
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def _save_question_queue(queue: list[str]) -> None:
    os.makedirs(os.path.dirname(_QUESTION_QUEUE_FILE), exist_ok=True)
    with open(_QUESTION_QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)


def pop_queued_question() -> str | None:
    """Pop the oldest queued follow-up question. Returns None if queue is empty."""
    queue = _load_question_queue()
    if not queue:
        return None
    question = queue.pop(0)
    _save_question_queue(queue)
    return question


def reason_response(
    state: BiologicalState,
    stimulus: str,
    emotion_result: "dict | None" = None,
    context_result: "dict | None" = None,
) -> dict:
    """
    Run the Conversation Pillar reasoning pass.

    emotion_result: Emotion Pillar output (SPEC-52). If provided, emotional_summary
                    is used instead of raw chemistry — richer deliberation context.
    context_result: Context Pillar output (SPEC-52). If provided, situational_summary
                    is included.

    Returns a dict with all fields from _REQUIRED_FIELDS.
    Raises RuntimeError if the pass fails after retries — callers should catch and log.
    """
    state_summary = _state_summary(state)
    stimulus_preview = stimulus[:400]

    parts = []
    if emotion_result and emotion_result.get("emotional_summary"):
        parts.append(f"Emotional state: {emotion_result['emotional_summary']}")
    else:
        parts.append(f"Her state: {state_summary}")

    if context_result and context_result.get("situational_summary"):
        parts.append(f"Situational context: {context_result['situational_summary']}")

    parts.append(f"The message: {stimulus_preview}")
    user_content = "\n".join(parts)

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user_content},
    ]

    result: dict | None = None
    for attempt in range(1, 4):
        response = chat_create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        token_stats.record_response("reasoner", response)
        raw = (response.choices[0].message.content or "").strip()

        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE).strip()

        try:
            parsed = json.loads(raw)
            missing = [k for k in _REQUIRED_FIELDS if k not in parsed]
            if missing:
                raise ValueError(f"missing fields: {missing}")
            if parsed.get("approach") not in VALID_APPROACHES:
                raise ValueError(f"invalid approach: {parsed.get('approach')!r}")
            result = parsed
            break
        except (json.JSONDecodeError, ValueError) as exc:
            log("REASONER/ERR", f"attempt {attempt}: {exc} — raw: {repr(raw[:120])}")
            if attempt < 3 and raw:
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": (
                        "Invalid JSON or missing/invalid fields. Return only a valid JSON object "
                        f"with all required fields: {', '.join(_REQUIRED_FIELDS)}. "
                        "approach must be one of: banter, sincere, question, deflect, "
                        "ignore, vulnerable, warm, brief."
                    )},
                ]

    if result is None:
        raise RuntimeError("Reasoning pass failed after 3 attempts")

    log("REASONER", (
        f"[{result['approach']}] {result['internal_reaction'][:80]} "
        f"→ {result['strategy_rationale'][:80]}"
    ))

    # Append new questions to the queue (accumulated across turns)
    new_questions = [q for q in (result.get("follow_up_questions") or []) if isinstance(q, str)]
    if new_questions:
        queue = _load_question_queue()
        queue.extend(new_questions)
        _save_question_queue(queue)
        log("REASONER/QUEUE", f"queued {len(new_questions)} question(s)")

    # Persist follow-up thoughts (overwrite — decay after one heartbeat cycle)
    thoughts = [t for t in (result.get("follow_up_thoughts") or []) if isinstance(t, str)]
    if thoughts:
        os.makedirs(os.path.dirname(_FOLLOW_UP_THOUGHTS_FILE), exist_ok=True)
        with open(_FOLLOW_UP_THOUGHTS_FILE, "w") as f:
            json.dump({"ts": time.time(), "thoughts": thoughts}, f, indent=2)

    try:
        from src.infrastructure.stream_bus import stream_bus
        stream_bus.emit("reasoning", {
            "approach": result["approach"],
            "tone": result.get("tone", ""),
            "internal_reaction": result["internal_reaction"][:120],
        })
    except Exception:
        pass

    return result


def format_strategy_block(result: dict, queued_question: str | None = None) -> str:
    """
    Serialize the reasoning result into a [Response Strategy] system prompt block.
    cortex.py calls this and appends the output to the assembled system prompt.
    """
    lines = [
        "[Response Strategy]",
        f"Approach: {result['approach']}",
        f"Tone: {result['tone']}",
        f"Lead with: {result['lead_with']}",
        f"Internal reaction (do not express directly): {result['internal_reaction']}",
    ]
    if result.get("subtext_detected"):
        lines.append(f"Subtext detected: {result['subtext_detected']}")
        lines.append(f"Lean into subtext: {'yes' if result.get('lean_into_subtext') else 'no'}")
    if queued_question:
        lines.append(f"Queued question (surface if the moment is right): {queued_question}")
    return "\n".join(lines)
