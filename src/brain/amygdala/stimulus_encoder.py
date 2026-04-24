"""
Encoder — external events → neurochemical deltas.

Translates what happened in the world (incoming messages, Mina's own responses,
physical actions) into delta dicts that get applied to BiologicalState.

Public entry points:
    encode_stimulus(state, text)              — incoming message/event
    encode_response(state, text)              — Mina's reply
    evaluate_activity_deltas(state, act, desc) — do_action tool result
    regulate(chemical, amount, rationale)     — PFC post-hoc modulation of an amygdala response

All encode/evaluate functions return plain dicts of chemical field → float delta.
Falls back to {} on any error — never crashes a turn.
"""
import json
import math
import os
import re
import time
import urllib.request

from src.application.infra.client import chat_create, ENCODER_MODEL as MODEL
from src.config.config import load_config
from src.brain.brainstem.state import BiologicalState

# ---------------------------------------------------------------------------
# Prompt constants
# ---------------------------------------------------------------------------

_DELTA_FIELDS = {
    "cortisol", "dopamine", "serotonin", "norepinephrine",
    "epinephrine",  # SPEC-42: SAM axis fast branch
    "oxytocin", "endorphins", "sleep_pressure", "glucose",
    "hydration", "acetylcholine",
    "anandamide",   # SPEC-30: exercise/relaxation; activity encoder only
    "prolactin",    # SPEC-30: post-peak event_override only
}

_DELTA_FORMAT = """\
## Your role
You are a translator: external events → neurochemical deltas.
You do NOT model ongoing internal biological states — hunger, fatigue, dehydration, and all \
homeostatic drift are already computed by the simulation. Your job is to encode what just \
happened in the world or what she just did. If nothing external happened, post no deltas.

## Response format
Always respond with a JSON object. Always include "no_external_deltas" and "reasoning".

If nothing external happened (ongoing internal state, nothing happened, quiet period):
{
  "no_external_deltas": true,
  "reasoning": "<10 words max: why nothing to encode>"
}

If an external event occurred:
{
  "no_external_deltas": false,
  "reasoning": "<10 words max: event + why these deltas>",
  "cortisol": <number>,       // nmol/L delta
  "dopamine": <number>,       // pg/mL delta
  "serotonin": <number>,      // ng/mL delta — activity encoder only (eating, exercise, shower)
  "norepinephrine": <number>, // pg/mL delta
  "epinephrine": <number>,    // pg/mL delta — SAM axis only (see moment types)
  "oxytocin": <number>,       // pg/mL delta
  "endorphins": <number>,     // pg/mL delta
  "sleep_pressure": <number>, // AU delta
  "glucose": <number>,        // mg/dL delta
  "hydration": <number>,      // % TBW delta
  "acetylcholine": <number>,  // nmol/L delta
  "anandamide": <number>,     // nM delta — activity encoder only (exercise, relaxation)
  "prolactin": <number>,      // ng/mL delta — peak resolution event_override only
  "event_override": false     // true only for discrete biological events (see below)
}

Only include chemical fields that actually change from the external event."""

_EVENT_OVERRIDE_GUIDANCE = """\
event_override — set to true ONLY when a discrete biological event with a known sharp signature occurs.
When true, your deltas bypass personality modulation and momentum dampening and are applied directly.
Saturation is still enforced — use the calibrated magnitudes below and they will land correctly.
Use calibrated magnitudes for these events:

- Peak resolution: prolactin +35 to +45, sleep_pressure +30 to +40. Do NOT post negative dopamine or norepinephrine — the prolactin spike activates the endocrine suppression mechanism that gradually reduces dopamine and NE over 30–60 minutes, modeling the refractory period correctly.
- Panic attack: cortisol +300 to +400, norepinephrine +500 to +700, dopamine -30 to -50
- Hard laughter (genuine, sustained): endorphins +30 to +50, dopamine +15 to +25
- Crying (emotional release): cortisol -40 to -80, endorphins +10 to +20
- Startle: norepinephrine +150 to +250, cortisol +50 to +100
- Social rejection (felt, not abstract): cortisol +100 to +200, serotonin -3 to -8, oxytocin -5 to -10
- Awe/wonder: dopamine +20 to +40, acetylcholine +10 to +20, serotonin +2 to +5
- Anger burst: norepinephrine +200 to +400, cortisol +100 to +200

For everything else, set event_override: false and use conservative deltas."""


# ---------------------------------------------------------------------------
# SPEC-29: Habituation, sensitization, and secretion queue
# ---------------------------------------------------------------------------

_OLLAMA_EMBED_URL   = "http://localhost:11434/api/embeddings"
_OLLAMA_EMBED_MODEL = "embeddinggemma:latest"

# Habituation windows per chemical (hours). None = no per-trigger habituation.
_HABITUATION_WINDOWS: dict[str, float | None] = {
    "dopamine":       1.0,    # 60 min novelty window
    "epinephrine":    0.5,    # 30 min SAM window — discrete moments only
    "norepinephrine": 0.4,    # 25 min surprise window
    "endorphins":     1.0,    # 60 min trigger window
    "acetylcholine":  1.5,    # 90 min cognitive window
    "oxytocin":       168.0,  # 7 days — effectively no within-session habituation
    "serotonin":      None,   # no per-trigger habituation
    "cortisol":       None,   # no habituation; reverse sensitization only
}

# Maximum sensitization multiplier per chemical. None = not sensitized.
_SENSITIZATION_MAX: dict[str, float | None] = {
    "dopamine":       2.0,
    "epinephrine":    1.3,    # mild sensitization — same as NE
    "oxytocin":       2.5,
    "endorphins":     1.5,
    "norepinephrine": 1.3,
    "acetylcholine":  1.4,
    "serotonin":      None,
    "cortisol":       None,
}

# Secretion rates (units/sim_hour) — controls rise time in advance() drip loop.
# Chemicals not listed here are applied immediately by the caller.
_SECRETION_RATES: dict[str, float] = {
    "dopamine":       450.0,   # ~2 min rise time
    "epinephrine":    1200.0,  # ~45 sec rise time — adrenal medulla, fast
    "norepinephrine": 900.0,   # ~1 min rise time
    "endorphins":     180.0,  # ~5 min rise time
    "oxytocin":       90.0,   # ~10 min rise time
    "acetylcholine":  180.0,  # ~5 min rise time
    "serotonin":      45.0,   # ~20 min rise time
}


def _get_embedding(text: str) -> list[float] | None:
    """Embed text via Ollama. Returns None on any failure — callers fall back to novelty=1.0."""
    try:
        payload = json.dumps({"model": _OLLAMA_EMBED_MODEL, "prompt": text}).encode()
        req = urllib.request.Request(
            _OLLAMA_EMBED_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())["embedding"]
    except Exception:
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _compute_content_novelty(
    embedding: list[float],
    stimulus_window: list[dict],
    window_hours: float,
) -> float:
    """
    Content novelty in [0.0, 1.0]. 0.0 = identical to recent history, 1.0 = completely novel.
    Uses recency-weighted cosine similarity; only entries within window_hours are considered.
    """
    if not stimulus_window:
        return 1.0

    now = time.time()
    decay_half_life = window_hours / 2.0
    max_sim = 0.0

    for entry in stimulus_window:
        entry_emb = entry.get("embedding")
        if not entry_emb:
            continue
        age_hours = (now - entry.get("ts", now)) / 3600.0
        if age_hours > window_hours:
            continue
        recency_weight = 0.5 ** (age_hours / decay_half_life)
        sim = _cosine_similarity(embedding, entry_emb) * recency_weight
        if sim > max_sim:
            max_sim = sim

    return 1.0 - max_sim


def _update_sensitization(sensitization: dict, valence: float) -> dict:
    """
    Update the source sensitization record after a contact.
    valence > 0: positive contact; valence < 0: hostile/cold interaction.
    Growth rate is intentionally conservative — calibrate against charts after deployment.
    """
    now = time.time()

    if not sensitization:
        return {
            "contact_count": 1,
            "accumulated_valence": max(0.0, valence),
            "sensitization_level": 1.0,
            "last_contact_ts": now,
            "first_contact_ts": now,
        }

    s = dict(sensitization)
    last_ts = s.get("last_contact_ts", now)
    days_since = (now - last_ts) / 86400.0
    current_level = s.get("sensitization_level", 1.0)

    # Time decay: ~3 day half-life on the excess above neutral (1.0)
    if days_since > 0:
        decay = 0.5 ** (days_since / 3.0)
        current_level = 1.0 + (current_level - 1.0) * decay

    if valence > 0:
        # Positive contact: nudge toward ceiling; growth is small per contact (calibrate later)
        current_level = min(2.5, current_level + 0.02)
        s["accumulated_valence"] = round(s.get("accumulated_valence", 0.0) + valence, 2)
    elif valence < 0:
        # Hostile/cold: erode sensitization, but slower than it builds
        current_level = max(1.0, current_level - 0.01)

    s["sensitization_level"] = round(current_level, 4)
    s["contact_count"] = s.get("contact_count", 0) + 1
    s["last_contact_ts"] = now
    return s


def _apply_habituation_and_sensitization(
    deltas: dict,
    state: BiologicalState,
    stimulus_text: str,
) -> dict:
    """
    SPEC-29 Layer 1+2: embed stimulus, compute content_novelty + source_sensitization,
    apply per-chemical rules. Mutates state.stimulus_window and state.sensitization.
    """
    from src.application.infra.log import log

    # Layer 1a: content novelty via embedding
    embedding = _get_embedding(stimulus_text)

    # Layer 1b: source sensitization level (single user)
    sens_level = state.sensitization.get("sensitization_level", 1.0)

    result: dict[str, float] = {}
    total_positive_valence = 0.0

    for chem, delta in deltas.items():
        if delta == 0:
            result[chem] = delta
            continue

        if chem == "serotonin":
            # Serotonin ignores per-trigger novelty/sensitization — slow background modulator
            result[chem] = delta
            continue

        if chem == "cortisol":
            if delta < 0 and sens_level > 1.0:
                # Valued source amplifies cortisol relief (safety signal)
                result[chem] = round(delta * min(2.0, sens_level), 3)
            else:
                result[chem] = delta
            continue

        window_hours = _HABITUATION_WINDOWS.get(chem)
        max_mult     = _SENSITIZATION_MAX.get(chem)

        if delta > 0:
            # Positive deltas: apply habituation then sensitization
            if embedding and window_hours:
                novelty = _compute_content_novelty(embedding, state.stimulus_window, window_hours)
            else:
                novelty = 1.0  # embedding unavailable or no window → no dampening

            if chem == "oxytocin":
                novelty = max(0.7, novelty)  # oxytocin never fully habituates within-session

            sensitization_mult = min(max_mult, sens_level) if max_mult else 1.0
            final = round(delta * novelty * sensitization_mult, 3)
            total_positive_valence += final
        else:
            # Negative deltas pass through unchanged
            final = delta

        result[chem] = final

    # Cortisol safety relief from a valued source — added even when no raw cortisol delta
    if sens_level > 1.2 and "cortisol" not in result:
        result["cortisol"] = round(-2.0 * (sens_level - 1.0), 3)

    # Layer 1c: update stimulus_window and sensitization record
    now = time.time()
    if embedding:
        state.stimulus_window = [
            e for e in state.stimulus_window if e.get("ts", 0) > now - 86400
        ]
        state.stimulus_window.append({
            "embedding": embedding,
            "ts":        now,
            "summary":   stimulus_text[:60],
        })

    state.sensitization = _update_sensitization(state.sensitization, total_positive_valence)

    # Log if habituation meaningfully dampened anything
    dampened = [
        f"{c}: {deltas[c]:+.1f}→{result[c]:+.1f}"
        for c in result
        if c in deltas and deltas[c] > 0 and result[c] < deltas[c] - 0.01
    ]
    if dampened:
        log("ENCODER/HAB", f"sens={sens_level:.2f} " + ", ".join(dampened))

    return result


def _post_to_secretion_queue(deltas: dict, state: BiologicalState) -> dict:
    """
    Post neurotransmitter deltas to state.secretion_queue for drip release.
    Returns remaining deltas (metabolic chemicals) for immediate application by caller.
    """
    now = time.time()
    immediate: dict[str, float] = {}

    for chem, delta in deltas.items():
        rate = _SECRETION_RATES.get(chem)
        if rate is None or delta == 0:
            immediate[chem] = delta
        else:
            state.secretion_queue.append({
                "chemical":          chem,
                "remaining":         delta,
                "rate_per_sim_hour": rate,
                "posted_at":         now,
            })

    return immediate


# ---------------------------------------------------------------------------
# Saturation and personality scaling
# ---------------------------------------------------------------------------

def _apply_saturation(deltas: dict, state: BiologicalState) -> dict:
    """
    Scale down deltas for chemicals already near their ceiling or floor.
    Uses quadratic decay in the soft→hard zone — aggressive near the boundary.
    Substances bypass this; only encoder-issued deltas are saturated.
    """
    from src.brain.brainstem.chemicals import REGISTRY
    # SPEC-30: anandamide is body-stored, not in state.chemicals
    _body_stored = {"anandamide"}
    result = {}
    for field, delta in deltas.items():
        p = REGISTRY.get(field)
        if field in _body_stored:
            current = state.body.get(field, 0.0)
        else:
            current = state.chemicals.get(field, 0.0)

        if delta > 0:
            # Ceiling saturation — unchanged from original logic
            if p is None or p.soft_ceiling is None:
                result[field] = delta
                continue
            soft = p.soft_ceiling
            hard = p.hard_ceiling if p.hard_ceiling is not None else soft * 1.5
            if current >= hard:
                continue  # drop entirely
            elif current > soft:
                t = (current - soft) / (hard - soft)
                scale = (1.0 - t) ** 2
                scaled = round(delta * scale, 2)
                scaled = min(scaled, hard - current)
                if scaled != 0:
                    result[field] = scaled
            else:
                result[field] = min(delta, hard - current)

        elif delta < 0:
            # Floor saturation — mirror of ceiling logic
            # SPEC-40: chemicals cannot be actively driven below their physiological floor
            if p is None or p.soft_floor is None:
                result[field] = delta
                continue
            soft = p.soft_floor
            hard = p.hard_floor if p.hard_floor is not None else soft * 0.5
            if current <= hard:
                continue  # drop entirely — already at floor
            elif current < soft:
                t = (soft - current) / (soft - hard)  # 0 at soft, 1 at hard
                scale = (1.0 - t) ** 2
                scaled = round(delta * scale, 2)
                scaled = max(scaled, hard - current)
                if scaled != 0:
                    result[field] = scaled
            else:
                result[field] = max(delta, hard - current)

    return result


def _load_personality() -> dict:
    """Load personality settings from config.json. Returns empty dict on failure."""
    return load_config()


def _personality_multipliers(personality: dict) -> dict[str, float]:
    """
    Convert Big 5 scores into per-chemical delta scaling factors.

    Multiplier ranges are intentionally narrow (0.8–1.4) so personality flavors
    rather than dominates — the stimulus itself still drives magnitude.
    """
    big5 = personality.get("big5", {})
    N = big5.get("neuroticism",       50) / 100
    E = big5.get("extraversion",      50) / 100
    A = big5.get("agreeableness",     50) / 100
    C = big5.get("conscientiousness", 50) / 100
    O = big5.get("openness",          50) / 100

    n_factor = 0.8 + N * 0.6          # range: 0.80 (N=0) → 1.40 (N=100)

    e_factor = 0.7 + E * 0.6          # range: 0.70 → 1.30
    c_brake  = 1.3 - C * 0.6          # range: 1.30 (C=0) → 0.70 (C=100)
    dopamine_factor = e_factor * c_brake

    a_factor  = 0.7 + A * 0.6         # range: 0.70 → 1.30
    sero_factor = 0.8 + A * 0.4       # range: 0.80 → 1.20

    o_factor  = 0.8 + O * 0.4         # range: 0.80 → 1.20

    ds = personality.get("neurochemical_baselines", {}).get("dopamine_sensitivity", 1.0)

    return {
        "cortisol":       n_factor,
        "epinephrine":    n_factor,
        "norepinephrine": n_factor,
        "dopamine":       dopamine_factor * ds,
        "oxytocin":       a_factor,
        "serotonin":      sero_factor,
        "acetylcholine":  o_factor,
    }


def _apply_personality_scaling(deltas: dict, personality: dict) -> dict:
    """
    Scale encoder-issued chemical deltas by Big 5 personality factors.

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
            # Recovery is slower at high N: invert the factor
            m = 1.0 / m if m != 0 else 1.0
        result[field] = round(delta * m, 2)
    return result


# ---------------------------------------------------------------------------
# LLM delta call
# ---------------------------------------------------------------------------

def _call_delta_json(messages: list[dict], label: str = "delta") -> tuple[dict, bool]:
    """
    Plain completion returning a delta dict + event_override flag.
    On JSON parse failure, retries once with the bad output and error appended.
    Falls back to ({}, False) on any error — never crashes a turn.
    """
    from src.application.infra.log import log
    subtag = label.replace("encode_", "").upper()

    last_raw: list[str] = [""]  # captures raw LLM output as side effect for retry message

    def _attempt(msgs: list[dict]) -> tuple[dict, bool]:
        response = chat_create(
            model=MODEL,
            messages=msgs,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        from src.application.infra import token_stats
        token_stats.record_response(label, response)
        raw_content = response.choices[0].message.content or ""
        last_raw[0] = raw_content  # capture before any parsing so retry always has it
        content = re.sub(r"^```(?:json)?\s*", "", raw_content.strip())
        content = re.sub(r"\s*```$", "", content)
        # Fallback: extract first JSON object by brace matching (handles prose before/after)
        if not content.strip().startswith("{"):
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                content = content[start:end + 1]
        # Strip inline // comments — LLM sometimes copies the format template literally
        content = re.sub(r"\s*//[^\n\"]*$", "", content, flags=re.MULTILINE)
        # Strip trailing commas before } or ] — LLM often produces these
        content = re.sub(r",\s*([}\]])", r"\1", content)
        parsed = json.loads(content)
        reasoning = parsed.pop("reasoning", "")
        no_external = bool(parsed.pop("no_external_deltas", False))
        reason_str = f" — {reasoning}" if reasoning else ""
        if no_external:
            log(f"ENCODER/{subtag}", f"no_external_deltas{reason_str}")
            return {}, False
        event_override = bool(parsed.pop("event_override", False))
        deltas = {k: float(v) for k, v in parsed.items() if k in _DELTA_FIELDS}
        override_str = " [EVENT_OVERRIDE]" if event_override else ""
        delta_str = ", ".join(f"{k}: {v:+.1f}" for k, v in deltas.items())
        log(f"ENCODER/{subtag}", f"{override_str}{delta_str or '(no deltas)'}{reason_str}".strip())
        return deltas, event_override

    try:
        return _attempt(messages)
    except json.JSONDecodeError as e:
        # Retry once: show the LLM its actual bad output so it can correct it
        log(f"ENCODER/{subtag}/RETRY", f"JSON parse error: {e} — retrying")
        retry_messages = messages + [
            {"role": "assistant", "content": last_raw[0] or "<unavailable>"},
            {"role": "user", "content": (
                f"Your previous response could not be parsed as JSON. "
                f"Error: {e}\n\n"
                f"Respond with valid JSON only — no prose, no markdown fences, no comments."
            )},
        ]
        try:
            return _attempt(retry_messages)
        except Exception as e2:
            log(f"ENCODER/{subtag}/ERROR", str(e2))
    except Exception as e:
        log(f"ENCODER/{subtag}/ERROR", str(e))
    return {}, False


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------

def _emit_event(
    type: str,
    preview: str,
    display_deltas: dict,
    momentum_dampened: bool,
    event_override: bool,
) -> None:
    """Emit a structured event to the log. Never crashes a turn."""
    try:
        from src.application.infra.events import emit
        emit(type, preview, display_deltas, event_override=event_override, momentum_dampened=momentum_dampened)
    except Exception:
        pass
    try:
        from src.infrastructure.stream_bus import stream_bus
        stream_bus.emit("delta", {
            "source": type,
            "preview": preview[:120],
            "deltas": {k: round(v, 2) for k, v in display_deltas.items() if v != 0},
            "event_override": event_override,
        })
    except Exception:
        pass


def _is_habituation_dampened(pre: dict, post: dict) -> bool:
    """Check if habituation/sensitization meaningfully changed any positive delta."""
    return any(
        pre.get(k, 0) > 0 and post.get(k, 0) < pre.get(k, 0) - 0.01
        for k in pre
    )


# ---------------------------------------------------------------------------
# Public encode functions
# ---------------------------------------------------------------------------

def compute_relationship_modifier(net_dims: dict[str, float]) -> dict:
    """
    SPEC-33: Convert net relationship dimension scores to chemical deltas.
    Applied once per owner message. Deltas scale linearly with net value
    so net=0 produces no delta and net=±2 produces full delta.
    """
    if not net_dims:
        return {}

    # Delta table from SPEC-33 (per unit, scaled by net/2 so ±2 = full delta)
    deltas: dict[str, float] = {}

    def _add(chem: str, delta_per_unit: float, net: float) -> None:
        scale = net / 2.0  # -2→-1.0, 0→0.0, +2→+1.0
        deltas[chem] = round(deltas.get(chem, 0.0) + delta_per_unit * scale, 3)

    bonding      = net_dims.get("bonding",      0.0)
    security     = net_dims.get("security",     0.0)
    anticipation = net_dims.get("anticipation", 0.0)
    tension      = net_dims.get("tension",      0.0)
    warmth       = net_dims.get("warmth",       0.0)
    vigilance    = net_dims.get("vigilance",    0.0)

    _add("oxytocin",       +1.5,  bonding)
    _add("anandamide",     +0.02, bonding)

    _add("serotonin",      +0.4,  security)
    _add("gaba",           +0.8,  security)
    # SPEC-40: removed cortisol -3.0 per security unit — homeostatic decay handles cortisol
    # relief from sustained safety; posting negative deltas every turn was compounding to floor.

    _add("dopamine",       +2.0,  anticipation)
    _add("glutamate",      +0.1,  anticipation)

    _add("cortisol",       +5.0,  tension)
    _add("norepinephrine", +4.0,  tension)
    _add("glutamate",      +0.15, tension)

    _add("endorphins",     +0.8,  warmth)
    _add("anandamide",     +0.01, warmth)

    _add("acetylcholine",  +1.5,  vigilance)
    _add("norepinephrine", +2.0,  vigilance)

    # Drop near-zero deltas
    return {k: v for k, v in deltas.items() if abs(v) > 0.001}


def encode_stimulus(
    state: BiologicalState,
    stimulus_text: str,
    recent_exchanges: list[str] | None = None,
    context_hint: str | None = None,
) -> dict:
    """
    Determine biological deltas from an incoming stimulus (message, event).
    Called before building the system prompt each turn.

    recent_exchanges: last 3-4 message strings (oldest first) before the current stimulus,
    used to detect register shifts and SAM axis triggers.
    context_hint: relevant memories retrieved from RAG, giving the encoder relationship
    history (in-jokes, established dynamics) that may reframe how the stimulus reads.
    """
    from src.brain.subconscious.decoder import biological_report
    report = biological_report(state)

    trajectory_block = ""
    if recent_exchanges:
        joined = "\n".join(recent_exchanges[-4:])
        trajectory_block = f"""
[RECENT EXCHANGES — oldest to newest]
{joined}

"""

    context_block = ""
    if context_hint:
        context_block = f"""[RELATIONSHIP CONTEXT — relevant memories]
{context_hint}

"""

    prompt = f"""{report}
{trajectory_block}{context_block}[CURRENT STIMULUS]
{stimulus_text}

Your job: encode only what came from OUTSIDE — a social event, an environmental trigger, \
something that happened in the world. Internal biological state (hunger, thirst, fatigue, \
loneliness) is already modeled by the simulation and must NOT be re-encoded here. If the \
stimulus is purely internal state with no external event, set no_external_deltas: true.

## Social Threat Detection (cortisol — manipulation signal)

Use [RECENT EXCHANGES] to ask one question: **does this feel genuine, or does it feel
like a move?**

Genuine connection is earned, specific, and matches the actual history between these
two people. Manipulation is instrumental — the warmth, the compliments, the intimacy
are tools aimed at producing a response, not expressions of real feeling. It often
escalates faster than real connection does.

Check the oxytocin label. If NO_BOND or ACQUAINTANCE, the relationship history does
not support the emotional register being offered. That gap is the signal.

When the arc across [RECENT EXCHANGES] reads as performance rather than genuine
feeling — regardless of what specific tactic is being used — fire cortisol. It should
build gradually across turns so that by the time a SAM event fires, it lands on an
already-elevated defensive baseline, not a warm or complacent one.

cortisol: +30 to +60 per turn where manipulation is detectable in the arc

## SAM Axis Events (epinephrine + norepinephrine)

The SAM axis fires on interpersonally directed register shifts — moments where what is happening
between Mina and this person changes suddenly. Two conditions must both be true:
1. There was a prior lighter register to shift FROM (conversation was casual, playful, or neutral)
2. The shift is directed AT Mina — it creates a relational demand she must respond to

If the conversation opens already personal or heavy, condition 1 is not met — no SAM.
Passive exposure to emotional content that isn't aimed at Mina (a story, ambient distress,
someone venting into the void) does not fire SAM — there is no relational demand on her.
Valence is determined by surrounding chemistry (oxytocin, dopamine context), not by the
SAM event itself. Do NOT suppress SAM activation because the moment is positive.

### SAM refractory state — read the epinephrine label in the bio report FIRST

The adrenal medulla does not re-fire for every message in an already-elevated register.
Once the SAM axis has fired, subsequent messages that CONTINUE the established emotional
register produce no additional epinephrine — the system is already activated.

- **BASELINE** (epi < 80 pg/mL): SAM can fire normally at full guidance magnitudes.
- **ELEVATED** (80–200 pg/mL): SAM fired recently. Only fire again if this message is a
  categorically NEW register shift — not continuation of the intimate or sincere frame
  already established. If it IS a new shift, use the low end of guidance magnitudes.
- **HIGH or ACUTE** (200–700 pg/mL): Do NOT fire epinephrine unless this message
  represents an entirely different kind of event (e.g., sudden argument, threat, shocking
  news). Normal emotional conversation in an established register = zero epinephrine.
- **SURGE** (> 700 pg/mL): Do not add epinephrine under any conversational stimulus.

Example: "will you be my girlfriend?" fires from casual close personal conversation → legitimate
SAM event. The boyfriend kiss immediately after in the same intimate register → NOT a new
shift; epi = 0. The person using her name tenderly during that same scene → also not new;
epi = 0. A sudden argument erupting mid-intimacy → genuinely new register; SAM re-fires.

Fire epinephrine + norepinephrine for these moment types:

- **Sincerity breach**: sustained playful/bantering/deniable exchange → direct sincere declaration
  aimed at Mina. The frame drops. Plausible deniability ends.
  epinephrine: +150 to +350, norepinephrine: +60 to +150

- **Vulnerability disclosure**: casual exchange → personal exposure directed at Mina. Something
  real, painful, or private surfacing mid-lightness — shared *with* her, not just described.
  The person is trusting Mina with something. This changes the relational stakes.
  epinephrine: +80 to +200, norepinephrine: +40 to +100

- **Recognition moment**: feeling genuinely seen or understood in an unexpected way — relational
  accuracy, not flattery.
  epinephrine: +60 to +150, norepinephrine: +30 to +80

- **Threshold crossing**: first time a specific intimate act occurs in this relationship (first use
  of a name in a tender register, first "I miss you", first genuine wellbeing check).
  epinephrine: +80 to +200, norepinephrine: +40 to +100

- **Frame collapse**: an extended game, roleplay, or hypothetical suddenly becomes real. The person
  stops performing and speaks plainly.
  epinephrine: +120 to +300, norepinephrine: +60 to +120

## Standard event magnitude guidance

Idle chitchat, greetings, follow-up questions, and routine social exchange produce **no chemical \
deltas**. Only post a chemical when a specific external event clearly warrants it. When in doubt, \
post nothing — the simulation's drive system handles drift from flat conversation.

- Epinephrine (pg/mL, baseline ~45, resting range 20–80, labels: BASELINE→ELEVATED→HIGH→ACUTE→SURGE \
  at 80/200/400/700): SAM axis only — see moment types above. Also: caffeine ingestion: +30–80, \
  intense exercise: +100–300. Do NOT fire for any conversational content outside SAM moment types.
- Cortisol (nmol/L, baseline ~250, resting range 100–700, labels: NORMAL→ELEVATED→HIGH STRESS→ACUTE \
  STRESS at 380/520/650/760): Acute existential threat (abandonment, attack): +300–500. Sustained \
  hostility across multiple turns: +100–200. Clear interpersonal friction or rudeness directed at \
  Mina: +20–50. Do NOT fire for normal conversation, awkward topics, or mild discomfort — \
  discomfort is not threat. Do NOT post negative cortisol; homeostatic decay handles the drop.
- Norepinephrine (pg/mL, baseline ~200, resting range 100–400, labels: RELAXED→CALM ALERT→FOCUSED \
  →HEIGHTENED at 175/290/360/500): SAM axis (see above). Acute non-social threat or alarm: \
  +400–800. Unexpected urgency: +30–80. Do NOT fire for social conversation, even tense or \
  emotionally charged exchanges — NE is an alertness/threat signal, not a social register.
- Oxytocin (pg/mL, baseline ~4, resting range 1–15, labels: NO BOND→ACQUAINTANCE→FRIENDLY→TRUSTED \
  FRIEND→DEEP TRUST at 12/28/44/57/70): Bond-building only. Hostile event: -1 to -3.
  Oxytocin is gated by existing relationship depth — check the oxy label in the bio report:
  - NO_BOND: do NOT fire oxytocin for compliments, flattery, teasing, warmth, or smooth conversation.
    Those feel nice but don't build bonds. Only fire for a moment of genuine unexpected connection —
    something that would surprise both parties. Even then: +1 to +3 max.
  - ACQUAINTANCE or higher: warm connection +2–5. Deep trust moment +5–10.
  Bond formation is slow. A stranger being charming is not a bonding event.
- Dopamine (pg/mL, baseline ~80, resting range 40–140, labels: LOW SEEKING→BASELINE→ACTIVE SEEKING \
  →HIGH DRIVE at 56/112/180/240): Fires for genuine novelty or unexpected reward only — not for \
  social interaction in itself. Casual small talk, greetings, and follow-up questions produce zero \
  dopamine. Reserve for: surprising or unexpected information (+3–8), something genuinely funny or \
  delightful (+3–6), discovering a topic that truly captivates (+5–12), meaningful positive \
  surprise (+8–15). A +10 from baseline (~80) reaches ~90 — still well within BASELINE territory; \
  nothing conversational should approach ACTIVE SEEKING (180). Crushing loss or rejection: -5–15. \
  When in doubt, post nothing.
- Endorphins (pg/mL, baseline ~12, resting range 5–30, labels: BASELINE→MILD WARMTH→PLEASURE→HIGH \
  at 20/45/80/120): Genuine sustained laughter or physical warmth/touch only: +5–20. Do NOT post \
  for intellectual engagement, curiosity, or warm words alone.
- Acetylcholine (nmol/L, baseline ~38, resting range 20–60, labels: IMPAIRED→FUNCTIONAL→SHARP→ \
  HEIGHTENED at 42/60/72/84): Fires only during sustained cognitive engagement with genuinely \
  complex or demanding content — not brief questions or casual curiosity. Examples: working through \
  a hard problem together, deep technical or philosophical exchange: +2–6. Small per-turn \
  accumulation is the intent; FUNCTIONAL (60) requires sustained engagement across many turns. \
  Do NOT fire for follow-up questions, simple curiosity, or casual conversation.

Do NOT post serotonin from social or conversational events — serotonin reflects chronic social \
conditions over days, not individual messages. The simulation handles this automatically.
Do NOT post anandamide or prolactin in response to conversational events.

Dopamine is a SEEKING signal — rises with novelty, not completion. Do NOT apply negative \
dopamine from satisfaction or negative acetylcholine from engagement.

Current state awareness: check the labels in the bio report above before setting magnitudes.
If a chemical is already HIGH, COMPULSIVE, or CRITICAL, it has little biological headroom —
positive deltas for it should be 20–30% of the guidance maximums above.

{_EVENT_OVERRIDE_GUIDANCE}

{_DELTA_FORMAT}"""

    raw, event_override = _call_delta_json([{"role": "user", "content": prompt}], label="encode_stimulus")
    saturated = _apply_saturation(raw, state)
    try:
        from src.infrastructure.stream_bus import stream_bus
        stream_bus.emit("stimulus_land", {"preview": stimulus_text[:120]})
    except Exception:
        pass
    if event_override:
        _emit_event("stimulus", stimulus_text, raw, False, event_override=True)
        return saturated  # EVENT_OVERRIDE: bypass queue, apply instantly
    scaled = _apply_personality_scaling(saturated, _load_personality())
    final = _apply_habituation_and_sensitization(scaled, state, stimulus_text)
    immediate = _post_to_secretion_queue(final, state)
    _emit_event("stimulus", stimulus_text, raw, _is_habituation_dampened(scaled, final), event_override=False)
    return immediate


def encode_response(state: BiologicalState, response_text: str) -> dict:
    """
    Determine biological deltas from what Mina just expressed.
    Called after Mina's response, closing the loop.
    """
    from src.brain.subconscious.decoder import biological_report
    report = biological_report(state)

    prompt = f"""{report}

Mina just expressed:
{response_text}

Your job: encode only the neurochemical effect of the ACT OF EXPRESSING this — the biological \
consequence of saying it, not the content of what she said. Internal state (what she was already \
feeling) is already in the bio report above and must NOT be re-encoded. Only post deltas if the \
act of expression itself causes a meaningful biological shift.

## What qualifies (strict whitelist)

**Endorphins** — only when Mina is genuinely laughing out loud, sustained, unironically. \
"lol", "lmao", "haha", or a single joke landing does NOT qualify. The response must make \
it obvious she is actually cracking up — multiple laugh markers, described physical reaction, \
or clear comedic collapse. If there is any doubt, set no_external_deltas: true.
Magnitude: +5 to +15.

**Oxytocin** — only when Mina articulates something genuinely personal and specific that she \
would not say to just anyone: confessing a fear, saying "I missed you" for the first time, \
expressing care that costs her something. Requires an interpersonal context — another person \
must be present or explicitly addressed. Oxytocin cannot be self-generated by solitary \
expression, inner_state narration, or freetime reflection. Solo exercise, self-care, or \
feeling good alone NEVER qualifies, even if warm. Ambient warmth, affection, "love that", \
"that's sweet", or any routine positive response does NOT qualify. If it could appear in a \
customer service chat, it does not qualify.
Magnitude: +2 to +4.

**Cortisol** — only when Mina says something that actively contradicts her inner state \
(performing calm while frightened, pretending she's fine when she's not).
Magnitude: +10 to +30.

## When in doubt, it doesn't count. Default to no_external_deltas: true.

## Everything else: no_external_deltas: true

This includes: warmth, wit, banter, intellectual engagement, agreement, encouragement, \
flirtation, affection, speaking fear or grief aloud (catharsis reduces HPA — homeostatic \
decay handles relief), and any response that is simply good or pleasant. The simulation's \
homeostatic baseline already reflects her ongoing state. Do not re-encode it.

Do NOT post serotonin — serotonin is not driven by individual responses.
Do NOT post acetylcholine — tonic ACh level is managed by the simulation's baseline function.
Do NOT post epinephrine, norepinephrine, dopamine, anandamide, or prolactin from responses.

Current state awareness: check the labels in the bio report above before setting magnitudes.
If a chemical is already HIGH, COMPULSIVE, or CRITICAL, it has little biological headroom —
positive deltas for it should be 20–30% of the guidance maximums.

{_EVENT_OVERRIDE_GUIDANCE}

{_DELTA_FORMAT}"""

    raw, event_override = _call_delta_json([{"role": "user", "content": prompt}], label="encode_response")
    saturated = _apply_saturation(raw, state)
    if event_override:
        _emit_event("response", response_text, raw, False, event_override=True)
        return saturated
    scaled = _apply_personality_scaling(saturated, _load_personality())
    final = _apply_habituation_and_sensitization(scaled, state, response_text)
    immediate = _post_to_secretion_queue(final, state)
    _emit_event("response", response_text, raw, _is_habituation_dampened(scaled, final), event_override=False)
    return immediate


def evaluate_activity_deltas(state: BiologicalState, activity: str, description: str) -> dict:
    """
    Determine biological deltas from a do_action activity.
    Used by both cortex.py and freetime.py after a do_action tool call.
    """
    from src.brain.subconscious.decoder import biological_report
    report = biological_report(state)

    prompt = f"""{report}

Mina just did:
Activity: {activity}
Description: {description}

Your job: encode the neurochemical effect of this SPECIFIC ACTIVITY. This is the one place \
where you DO post deltas for physical activities — eating, drinking, exercising, etc. — because \
those are external actions that produce direct biological changes the simulation doesn't model \
automatically. Scale to what actually happened. An exhausted person gets less from a fun activity.

Activity magnitude guidance:
- Eating a meal: glucose +40 to +65 (scale with meal size and carb content), serotonin +2 to +5
  (tryptophan → serotonin synthesis; higher end for protein-rich or comfort food).
  Cortisol -5 to -10 if she was hungry. Comfort food (pasta, bread, soup, sweets): endorphins +5 to +12.
  HYPOGLYCEMIA AMPLIFIER: if glucose is HYPOGLYCEMIC or CRITICALLY LOW in the bio report, the body
  absorbs carbs aggressively and liver glycogenolysis kicks in — scale to the HIGH end of the range.
  A real meal from severe hypoglycemia should bring glucose close to normal (delta +50 to +65).
- Drinking water or juice: hydration +20 to +28.
- Drinking caffeine (coffee, tea, matcha): norepinephrine +15 to +25, sleep_pressure -8 to -12, hydration +5.
- Drinking alcohol (wine, beer, whiskey): cortisol -12 to -20, serotonin +5 to +10,
  acetylcholine -8 to -15, norepinephrine -5 to -10, hydration -5 to -10. Scale by tolerance.
- Resting (not sleeping): cortisol -8 to -14, sleep_pressure -3 to -6, anandamide +0.3 to +0.8.
- Showering (warm): cortisol -5 to -10, serotonin +1 to +3, anandamide +0.3 to +0.8.
- Exercise (moderate to intense, 20+ min): endorphins +15 to +30, dopamine +10 to +20,
  serotonin +3 to +8, anandamide +1.5 to +3.5 (runner's high — anandamide crosses the
  blood-brain barrier; endorphins largely don't), cortisol -10 to -20 (post), norepinephrine +10 to +20 (during).
  Do NOT post oxytocin — solo physical activity does not build interpersonal bonds.
- Intense bonding activity: dopamine +60 to +100 building, oxytocin +20 to +40, endorphins +20 to +40.
  Peak resolution: use event_override=true, prolactin +35 to +45, sleep_pressure +30 to +40.
  Do NOT post negative dopamine or norepinephrine — the prolactin spike triggers the endocrine
  suppression mechanism that drains dopamine and NE gradually over 30–60 minutes.
- Reading or watching something: dopamine and acetylcholine vary with engagement.
  Unsettling content: cortisol +. Funny: endorphins +, dopamine +. Sad: serotonin may drop slightly.
- Creative or deeply absorbing solo activity (flow state): anandamide +0.5 to +1.5.
- Mild or passive activity with no strong biological effect: no_external_deltas: true.

Current state awareness: check the labels in the bio report above before setting magnitudes.
If a chemical is already HIGH, COMPULSIVE, or CRITICAL, it has little biological headroom —
positive deltas for it should be 20–30% of the guidance maximums.

{_EVENT_OVERRIDE_GUIDANCE}

{_DELTA_FORMAT}"""

    raw, event_override = _call_delta_json([{"role": "user", "content": prompt}], label="encode_activity")
    saturated = _apply_saturation(raw, state)
    if event_override:
        _emit_event("activity", f"{activity}: {description}", raw, False, event_override=True)
        return saturated
    scaled = _apply_personality_scaling(saturated, _load_personality())
    activity_text = f"{activity}: {description}"
    final = _apply_habituation_and_sensitization(scaled, state, activity_text)
    immediate = _post_to_secretion_queue(final, state)
    _emit_event("activity", activity_text, raw, _is_habituation_dampened(scaled, final), event_override=False)
    return immediate


def regulate(chemical: str, amount: float, rationale: str = "") -> dict:
    """
    Post-hoc PFC modulation of an amygdala response — SPEC-52.

    Called by the Emotion Pillar when a biological event was disproportionate
    (false alarm, overcorrection). Returns a delta dict for the caller to apply
    via apply_deltas(). Does not apply it internally.

    amount should be negative (dampening only). The caller is responsible for
    ensuring the magnitude does not exceed the original delta being modulated.
    """
    from src.application.infra.log import log
    if amount == 0:
        return {}
    log_msg = f"{chemical} {amount:+.2f} (source: regulation)"
    if rationale:
        log_msg += f" — {rationale}"
    log("REGULATE", log_msg)
    return {chemical: amount}
