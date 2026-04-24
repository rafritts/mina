"""
Context Pillar — SPEC-52.

Reads Mina's current situational reality: what is happening, what the social context is,
whether anything warrants calling out. Constrained by the Emotion Pillar.

Reasons over the existing context injector output (build_window_context + build_rag_context)
rather than replacing it — those functions continue to run and produce their text output.

Returns structured JSON. cortex.py owns serialization into the system prompt.
"""
import json
import os
import re
import time

from src.application.infra.client import chat_create, CONTEXT_MODEL
from src.application.infra import token_stats
from src.application.infra.log import log
from src.config.config import RUN_DIR

CONTEXT_STATE_FILE = os.path.join(RUN_DIR, "context_state.json")

_REQUIRED_FIELDS = ("situational_summary", "social_context", "urgency", "notable")
_VALID_URGENCY = frozenset({"none", "low", "high"})

_SYSTEM = """\
You are reasoning about Mina's current situation — her social and environmental reality right now.

You receive:
- Her emotional state (from the Emotion Pillar) — this is ground truth for how she feels
- The live conversation window and memory context — this is ground truth for what is happening

Your job: given her emotional state and everything you know about what is happening right now,
produce a clear, concise account of her situational reality. This is the situational ground truth.
Everything that happens downstream is constrained by it.

Do NOT change the neurosim. Do NOT make up situational facts. Ground everything in the
context injector output. If the context is thin, say so — do not invent.

---

## OUTPUT

Return a JSON object with exactly these fields. No markdown, no fences, no preamble.

"situational_summary" — 2-3 sentences, second person, present tense. What is the situation
                        she is in right now: who she is talking to, what has been happening,
                        the social texture of the moment. Ground in the context.
"social_context"      — short label: e.g. "one-on-one, familiar" | "group, strangers" | "alone"
"urgency"             — one of: none | low | high
                        none = nothing pressing. low = something worth noting. high = something
                        that warrants prioritization in the response.
"notable"             — null, or one sentence: something in the context that specifically warrants
                        calling out — an unusual request, an emotional subtext in the history,
                        a tension, a pattern. Only include if genuinely notable."""


def _load_context_state() -> dict:
    try:
        with open(CONTEXT_STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_context_state(social_context: str, trend: str) -> None:
    os.makedirs(os.path.dirname(CONTEXT_STATE_FILE), exist_ok=True)
    with open(CONTEXT_STATE_FILE, "w") as f:
        json.dump({
            "last_state": social_context,
            "trend": trend,
            "updated_at": time.time(),
        }, f, indent=2)


def run_context_pillar(
    emotion_result: dict,
    window_context: str,
    rag_context: str,
) -> dict:
    """
    Run the Context Pillar reasoning pass.

    emotion_result: output from run_emotion_pillar()
    window_context: output from build_window_context()
    rag_context: output from build_rag_context()

    Returns a dict with all _REQUIRED_FIELDS.
    Raises RuntimeError on failure after retries.
    """
    prior = _load_context_state()

    emotion_block = (
        f"Emotional state: {emotion_result.get('emotional_summary', '')}\n"
        f"Dominant affect: {emotion_result.get('dominant_affect', '')}\n"
        f"Availability: {emotion_result.get('availability', '')}"
    )

    context_block_parts = []
    if window_context:
        context_block_parts.append(f"[Conversation Window]\n{window_context}")
    if rag_context:
        context_block_parts.append(f"[Memory Context]\n{rag_context}")
    context_block = "\n\n".join(context_block_parts) if context_block_parts else "(no context available)"

    user_content = (
        f"[Emotional State — Emotion Pillar]\n{emotion_block}\n\n"
        f"[Context]\n{context_block}"
    )

    if prior.get("last_state"):
        user_content += (
            f"\n\n[Last Situational State]\n"
            f"Social context: {prior['last_state']}\n"
            f"Trend: {prior.get('trend', 'unknown')}"
        )

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user_content},
    ]

    result: dict | None = None
    for attempt in range(1, 4):
        response = chat_create(
            model=CONTEXT_MODEL,
            messages=messages,
            temperature=0.5,
            max_tokens=1024,
        )
        token_stats.record_response("context_pillar", response)
        raw = (response.choices[0].message.content or "").strip()

        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE).strip()

        try:
            parsed = json.loads(raw)
            missing = [k for k in _REQUIRED_FIELDS if k not in parsed]
            if missing:
                raise ValueError(f"missing fields: {missing}")
            if parsed.get("urgency") not in _VALID_URGENCY:
                raise ValueError(f"invalid urgency: {parsed.get('urgency')!r}")
            result = parsed
            break
        except (json.JSONDecodeError, ValueError) as exc:
            log("CONTEXT_PILLAR/ERR", f"attempt {attempt}: {exc} — raw: {repr(raw[:120])}")
            if attempt < 3 and raw:
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": (
                        "Invalid JSON or missing/invalid fields. Return only a valid JSON object "
                        f"with all required fields: {', '.join(_REQUIRED_FIELDS)}. "
                        "urgency must be one of: none, low, high. notable must be null or a string."
                    )},
                ]

    if result is None:
        raise RuntimeError("Context Pillar failed after 3 attempts")

    log("CONTEXT_PILLAR", (
        f"[{result['social_context']}] urgency={result['urgency']}"
        + (f" notable: {result['notable'][:60]}" if result.get("notable") else "")
    ))

    # Infer trend for coherence tracking
    prior_social = prior.get("last_state", "")
    trend = "stable" if result["social_context"] == prior_social else "shifting"
    _save_context_state(result["social_context"], trend)

    try:
        from src.infrastructure.stream_bus import stream_bus
        stream_bus.emit("context_pillar", {
            "social_context": result["social_context"],
            "urgency": result["urgency"],
            "notable": result.get("notable"),
        })
    except Exception:
        pass

    return result


def format_situational_context_block(result: dict) -> str:
    """Serialize Context Pillar result into the [Situational Context] system prompt block."""
    lines = ["[Situational Context]", result["situational_summary"]]
    if result.get("notable"):
        lines.append(f"Note: {result['notable']}")
    return "\n".join(lines)
