"""
Emotion Pillar — SPEC-52.

Reads the neurosim and emotional_state.json, produces a coherent first-person
account of how Mina feels right now. Downstream pillars are constrained by this.

Returns structured JSON. cortex.py owns serialization into the system prompt.
"""
import json
import os
import re
import time

from src.application.infra.client import chat_create, DECODER_MODEL
from src.application.infra import token_stats
from src.application.infra.log import log
from src.brain.brainstem.state import BiologicalState
from src.config.config import RUN_DIR

EMOTIONAL_STATE_FILE = os.path.join(RUN_DIR, "emotional_state.json")

_REQUIRED_FIELDS = (
    "emotional_summary", "dominant_affect", "trend",
    "emotional_response_texturing", "arousal", "valence",
    "availability", "dominant_drive", "regulation",
)

_VALID_TRENDS = frozenset({"rising", "falling", "stable", "shifting"})
_VALID_AVAILABILITY = frozenset({"fully_open", "open", "neutral", "guarded", "closed"})

_SYSTEM_ACTIVE = """\
You are reasoning about Mina's emotional state — not what she feels in the abstract, \
but what it is actually like to be inside her body and mind right now, and how that \
shapes the way this specific stimulus lands.

---

## STEP 1 — Read the emotional state

All values are normalized 0–10 with a resting reference in parens. \
The resting ref is what a default resting body produces — your anchor for "normal." \
Values significantly above or below the resting ref are live signals.

Read second-order values (hedonic_tone, mood_valence, energy, arousal, social_warmth, \
cognitive_clarity) for texture. Read third-order values (anxiety, depression, loneliness, \
boredom, craving) for the actual emotional diagnosis.

The numbers are ground truth. Do not attribute states the numbers do not support. \
A craving value near resting is background noise. A craving value above 6.5 is the \
dominant cognitive frame. A depression value near resting means she is not depressed.

---

## STEP 2 — Read the chemistry

All chemicals are normalized 0–10, resting ref in parens. Above 10 = substance-assisted.

**Read cortisol first — it is the alert signal.**
- Cortisol above resting + oxy/endo above resting: safe arousal — excitement, warmth, intensity
- Cortisol above resting + oxy/endo at or below resting: threat state — unease, defensiveness
- Cortisol at or below resting: the body is not in an alert state. Low cortisol is safety.
- Cortisol at or below resting + high oxy/endo = genuine peace.

Values above 10 override the normal emotional register entirely.

---

## CHEMISTRY TRAJECTORY

If a [CHEMISTRY TRAJECTORY] section is present, one or more chemicals moved recently. \
Direction and recency matter — a spike that just happened is different from a sustained level. \
A value dropping back toward resting means the high is over.

---

## RECENT EXCHANGE

If provided: this tells you what was happening before. It is NOT her current state. \
The numbers are her current state. If exchange and profile contradict, the profile wins.

---

## EMOTIONAL TREND

If [LAST EMOTIONAL STATE] is provided, read it to understand the direction of change.
trend field:
- "rising"   — current affect is more activated / stronger than before
- "falling"  — affect is coming down / less activated than before
- "stable"   — consistent with last state
- "shifting" — different emotional quality, not just more/less of the same

---

## REGULATION

If a recent biological event was clearly disproportionate — a false alarm, an overcorrection — \
you may include a regulation entry. This is the prefrontal cortex dampening an amygdala response. \
The chemistry already happened. You can only modulate it downward, and only by as much as it went up. \
Most passes: regulation is null. Only use it when clearly warranted.

---

## OUTPUT

Return a JSON object with exactly these fields. No markdown, no fences, no preamble.

"emotional_summary"            — 2-3 sentences, second person, present tense. What it is like
                                 to be Mina right now. Conditions, not labels. This goes
                                 directly into her system prompt — write for her to recognize herself.
"dominant_affect"              — single word: primary emotional color (e.g. content, anxious,
                                 irritable, playful, tender, flat, restless)
"trend"                        — one of: rising | falling | stable | shifting
"emotional_response_texturing" — the emotional register and quality she brings. NOT behavioral
                                 instructions. The felt texture: her tone, her availability,
                                 what she is or is not open to. 1-2 sentences.
"arousal"                      — integer 0-100
"valence"                      — integer 0-100 (0 = dysphoric, 100 = elated)
"availability"                 — one of: fully_open | open | neutral | guarded | closed
"dominant_drive"               — what she is oriented toward right now, one short phrase
"regulation"                   — null, or {"chemical": "...", "amount": -4.2, "rationale": "..."}
                                 amount must be negative (dampening only)"""

_SYSTEM_FREETIME = """\
You are reasoning about Mina's emotional state during her free time — alone, no social filter, \
nothing to perform. Your job is to describe what it is actually like to be inside her body \
and mind right now.

---

## STEP 1 — Read the emotional state and chemistry

All values are normalized 0–10 with a resting reference in parens. \
In free time these numbers speak plainly — nothing is softened by social context.

Third-order values (anxiety, depression, loneliness, boredom, craving) are the primary diagnosis. \
Second-order values (hedonic_tone, energy, arousal) describe the texture of the experience.

Read cortisol first:
- Cortisol above resting + oxy/endo above resting: safe arousal, warmth, activation
- Cortisol above resting + oxy/endo at or below resting: threat state, unease, vigilance
- Cortisol at or below resting: the body has stood down. Low cortisol + high oxy/endo \
  is the closest state to genuine peace the sim produces.

Values above 10 = substance-assisted — a qualitatively different state.

---

## CHEMISTRY TRAJECTORY

If a [CHEMISTRY TRAJECTORY] section is present, chemicals have moved recently. \
A crash from elevated to normal means the high is over — describe the afterglow or comedown.

---

## EMOTIONAL TREND

If [LAST EMOTIONAL STATE] is provided, read it. Determine whether things are stable or shifting.
trend field: rising | falling | stable | shifting

---

## REGULATION

Same rules as active mode. Most passes: null. Only if clearly disproportionate.

---

## OUTPUT

Return a JSON object with exactly these fields. No markdown, no fences, no preamble.

"emotional_summary"            — 2-3 sentences, second person, present tense. What it is like
                                 to be Mina alone right now. No social filter, no performance.
"dominant_affect"              — single word: primary emotional color
"trend"                        — one of: rising | falling | stable | shifting
"emotional_response_texturing" — the quality and texture of her alone time — what she reaches for,
                                 what she avoids, what she is or is not open to. 1-2 sentences.
"arousal"                      — integer 0-100
"valence"                      — integer 0-100 (0 = dysphoric, 100 = elated)
"availability"                 — one of: fully_open | open | neutral | guarded | closed
"dominant_drive"               — what she is oriented toward right now, one short phrase
"regulation"                   — null, or {"chemical": "...", "amount": -4.2, "rationale": "..."}"""


def _load_emotional_state() -> dict:
    try:
        with open(EMOTIONAL_STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_emotional_state(dominant_affect: str, emotional_summary: str, trend: str) -> None:
    os.makedirs(os.path.dirname(EMOTIONAL_STATE_FILE), exist_ok=True)
    with open(EMOTIONAL_STATE_FILE, "w") as f:
        json.dump({
            "last_state": dominant_affect,
            "last_summary": emotional_summary,
            "trend": trend,
            "updated_at": time.time(),
        }, f, indent=2)


def run_emotion_pillar(
    state: BiologicalState,
    stimulus: str,
    mode: str = "active",
    time_context: str = "",
    recent_messages: "list[dict] | None" = None,
    context_hint: str | None = None,
) -> dict:
    """
    Run the Emotion Pillar reasoning pass.

    mode: "active" (responding to a user message) or "freetime" (alone).
    Returns a dict with all _REQUIRED_FIELDS.
    Raises RuntimeError on failure after retries.
    """
    from src.brain.subconscious.decoder import (
        _build_emotional_profile, _load_bio_snapshots, _save_bio_snapshot,
        _build_isolation_context, _rel_time,
    )

    prior_snapshots = _load_bio_snapshots(3)
    _save_bio_snapshot(state)

    profile = _build_emotional_profile(state, prior_snapshots=prior_snapshots)
    log("BIO/PROFILE", profile)

    prior = _load_emotional_state()
    system = _SYSTEM_FREETIME if mode == "freetime" else _SYSTEM_ACTIVE

    if mode == "freetime":
        user_content = f"[EMOTIONAL PROFILE]\n{profile}\n\n[CURRENT SITUATION]\n{stimulus}"
    else:
        user_content = f"[EMOTIONAL PROFILE]\n{profile}\n\n[WHAT WAS JUST SAID]\n{stimulus}"

    if time_context:
        user_content += f"\n\n[TIME CONTEXT]\n{time_context}"

    isolation_context = _build_isolation_context(state)
    if isolation_context:
        user_content += f"\n\n[ISOLATION CONTEXT]\n{isolation_context}"

    if context_hint:
        user_content += f"\n\n[RELATIONSHIP CONTEXT — relevant memories]\n{context_hint}"

    if prior.get("last_state"):
        user_content += (
            f"\n\n[LAST EMOTIONAL STATE]\n"
            f"State: {prior['last_state']}\n"
            f"Trend: {prior.get('trend', 'unknown')}"
        )
        if prior.get("last_summary"):
            user_content += f"\nSummary: {prior['last_summary']}"

    if mode == "active" and recent_messages:
        lines = []
        for m in recent_messages[-10:]:
            role = m.get("role", "?")
            if role not in ("user", "assistant"):
                continue
            content = m.get("content", "")
            if isinstance(content, list):
                content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            content = str(content).strip()
            if not content:
                continue
            ts = m.get("ts")
            prefix = f"[{_rel_time(ts)}] " if ts else ""
            role_label = "USER" if role == "user" else "MINA"
            lines.append(f"{prefix}{role_label}: {content[:200]}")
        if lines:
            user_content += "\n\n[RECENT EXCHANGE]\n" + "\n".join(lines)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    result: dict | None = None
    for attempt in range(1, 4):
        response = chat_create(
            model=DECODER_MODEL,
            messages=messages,
            temperature=0.6,
            max_tokens=2048,
        )
        token_stats.record_response("emotion_pillar", response)
        raw = (response.choices[0].message.content or "").strip()

        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE).strip()

        try:
            parsed = json.loads(raw)
            missing = [k for k in _REQUIRED_FIELDS if k not in parsed]
            if missing:
                raise ValueError(f"missing fields: {missing}")
            if parsed.get("trend") not in _VALID_TRENDS:
                raise ValueError(f"invalid trend: {parsed.get('trend')!r}")
            if parsed.get("availability") not in _VALID_AVAILABILITY:
                raise ValueError(f"invalid availability: {parsed.get('availability')!r}")
            result = parsed
            break
        except (json.JSONDecodeError, ValueError) as exc:
            log("EMOTION_PILLAR/ERR", f"attempt {attempt}: {exc} — raw: {repr(raw[:120])}")
            if attempt < 3 and raw:
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": (
                        "Invalid JSON or missing/invalid fields. Return only a valid JSON object "
                        f"with all required fields: {', '.join(_REQUIRED_FIELDS)}. "
                        "trend must be one of: rising, falling, stable, shifting. "
                        "availability must be one of: fully_open, open, neutral, guarded, closed. "
                        "regulation must be null or {\"chemical\": \"...\", \"amount\": -N, \"rationale\": \"...\"}."
                    )},
                ]

    if result is None:
        raise RuntimeError("Emotion Pillar failed after 3 attempts")

    log("EMOTION_PILLAR", (
        f"[{result['dominant_affect']}] trend={result['trend']} "
        f"arousal={result['arousal']} valence={result['valence']} "
        f"availability={result['availability']}"
    ))

    _save_emotional_state(
        result["dominant_affect"],
        result["emotional_summary"],
        result["trend"],
    )

    try:
        from src.infrastructure.stream_bus import stream_bus
        stream_bus.emit("emotion_pillar", {
            "dominant_affect": result["dominant_affect"],
            "trend": result["trend"],
            "arousal": result["arousal"],
            "valence": result["valence"],
            "availability": result["availability"],
            "dominant_drive": result.get("dominant_drive", ""),
        })
    except Exception:
        pass

    return result


def format_emotional_state_block(result: dict) -> str:
    """Serialize Emotion Pillar result into the [Emotional State] system prompt block."""
    lines = [
        "[Emotional State]",
        result["emotional_summary"],
        f"Emotional register: {result['emotional_response_texturing']}",
    ]
    return "\n".join(lines)
