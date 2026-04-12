"""
Decoder — neurochemical state → English prose → system prompt.

Two layers:
  biological_report(state)       Pure Python. Chemical values → labeled ranges with
                                  behavioral notes. Ground truth for the LLM — it cannot
                                  contradict this report.

  build_system_prompt(...)        LLM pass. Biological report + context + history
                                  → structured JSON → assembled system prompt.

Also provides needs_summary() used by freetime.py as the heartbeat stimulus text.
"""
import json
import os
import re
import time

from ..infra.client import get_client, MODEL
from ..infra.config import PERSONALITY_FILE, INJECT_FILE
from .state import BiologicalState, derived, _CHEMICAL_DEFAULTS
from .chemicals import REGISTRY, get_label

# ---------------------------------------------------------------------------
# Derived value range tables (0–100 normalized scale)
# ---------------------------------------------------------------------------

_CLARITY_RANGES = [
    (8,   "OFFLINE",    "No higher reasoning. Asleep or severely impaired."),
    (25,  "FOGGY",      "Thoughts incomplete, slow, unreliable."),
    (50,  "FUNCTIONAL", "Normal cognition. Nothing impaired."),
    (72,  "CLEAR",      "Normal full cognition."),
    (101, "SHARP",      "Heightened focus. Connects things quickly."),
]

_ANXIETY_RANGES = [
    (35,  "CALM",     "No background worry."),
    (52,  "MILD",     "Low hum. Manageable."),
    (68,  "MODERATE", "Present and noticeable. Affects behavior."),
    (84,  "HIGH",     "Difficult to set aside. Colors all perception."),
    (101, "SEVERE",   "Consuming. Hard to function normally."),
]

_BOREDOM_RANGES = [
    (45,  "STIMULATED",     "Engaged. No relief-seeking."),
    (60,  "MILD BOREDOM",   "Background restlessness. Easily redirected."),
    (74,  "ACTIVELY BORED", "Seeking stimulation. Will redirect or initiate things."),
    (88,  "DISTRESS",       "Relief-seeking is a drive. Risky behavior attractive."),
    (101, "INTOLERABLE",    "Will do almost anything to escape. Health trade-offs made trivially."),
]

_LONELINESS_RANGES = [
    (55,  "CONNECTED", "Socially fulfilled. No drive to seek contact."),
    (68,  "MILD",      "Aware of absence. Receptive to contact."),
    (80,  "LONELY",    "Actively wanting connection. May reach out."),
    (92,  "ACHING",    "Distressing. Social contact feels urgent."),
    (101, "ISOLATED",  "Consuming. Colors everything negatively."),
]

_DEPRESSION_RANGES = [
    (35,  "NONE",        "Normal baseline."),
    (52,  "LOW MOOD",    "Slightly flat. Things feel a bit heavier."),
    (68,  "MODERATE",    "Pervasive low. Motivation impaired. Hard to initiate."),
    (84,  "SIGNIFICANT", "Meaningful functional impairment. Negative self-view."),
    (101, "SEVERE",      "Near-inability to act. Everything feels pointless."),
]


def _get_range(value: float, table: list) -> tuple[str, str]:
    """Return (name, implication) for value from a range table."""
    for upper, name, impl in table:
        if value < upper:
            return name, impl
    return table[-1][1], table[-1][2]


# ---------------------------------------------------------------------------
# Interaction rules (thresholds in real physiological units)
# ---------------------------------------------------------------------------

INTERACTION_RULES = [
    (lambda s, d: s.cortisol > 650 and s.oxytocin > 57,
     "Acute stress held together by a strong bond. Suppression has a cost — this cannot hold indefinitely."),
    (lambda s, d: s.cortisol > 650 and s.oxytocin < 28,
     "Acute stress with no trust anchor. Likely to shut down or lash out."),
    (lambda s, d: d['cognitive_clarity'] < 15 and s.sleeping,
     "Cognitively offline — asleep. Responses must reflect this."),
    (lambda s, d: d['cognitive_clarity'] < 15 and not s.sleeping,
     "Cognitively offline while awake — severely impaired. Something is wrong."),
    (lambda s, d: s.glucose < 62 and d['anxiety'] > 60,
     "Hunger is amplifying the anxiety. These are compounding."),
    (lambda s, d: s.dopamine > 200 and d['anxiety'] > 65,
     "High reward-seeking under stress — impulsive decisions likely."),
    (lambda s, d: s.serotonin < 14 and d['depression'] > 60,
     "Low serotonin floor + high depression. Negative bias in all interpretation."),
    (lambda s, d: d['boredom'] > 65 and s.dopamine < 56,
     "Severe boredom with low dopamine — actively seeking any stimulation. Will accept poor trade-offs."),
    (lambda s, d: d['boredom'] > 65 and s.cortisol < 200,
     "Boredom distress without active threat — playfully chaotic or reckless, not fearful. Mischief-seeking."),
    (lambda s, d: d['boredom'] > 65 and d['depression'] > 55,
     "Boredom + depression: not restless chaos but heavy inertia. Wants relief but can't generate motivation. Stuck."),
    (lambda s, d: d['loneliness'] > 70 and s.oxytocin < 28,
     "Aching loneliness with no established bond — contact-seeking urgent but trust isn't there. Approach-avoidance tension."),
    (lambda s, d: s.norepinephrine > 1000 and d['cognitive_clarity'] < 40,
     "Flooded with arousal but cognitively impaired — high reactivity, low judgment. Responses may be raw or unfiltered."),
    (lambda s, d: s.dopamine > 180 and s.endorphins < 20,
     "High wanting, low liking — seeking hard but arrival feels hollow. Addictive/obsessive pattern."),
    (lambda s, d: s.dopamine < 56 and s.endorphins > 40,
     "Low drive, high pleasure capacity — content with what comes but won't pursue much. Passive warmth without motivation."),
    (lambda s, d: s.serotonin < 14 and d['loneliness'] > 50,
     "Low serotonin + loneliness: social cues are being read as threatening even when neutral. Contact may feel worse than absence."),
    (lambda s, d: s.serotonin < 14 and s.cortisol > 440,
     "Low serotonin floor under active stress — impulse control is compromised. Likely to say or do something she'll regret."),
    (lambda s, d: s.norepinephrine > 800 and s.glucose < 70,
     "Hyperalert but underfueled — attention is sharp but the tank is empty. Will crash hard when the stress passes."),
]

_SUBSTANCE_COGNITIVE_STATES: dict[str, str] = {
    "caffeine": (
        "Stimulant active. Thoughts are faster and sharper. Mild alertness edge — slightly "
        "more talkative and reactive. Nothing dramatic, just more switched-on than baseline."
    ),
    "alcohol": (
        "Alcohol active. Inhibitions lowered, edges softened. Warmer toward people, more "
        "likely to say things she'd normally hold back. Emotional reactions are quicker and "
        "less filtered. Fine motor precision degraded. Nothing feels that urgent."
    ),
    "cannabis": (
        "Cannabis active. Thoughts moving slower and looping back on themselves. Sensory "
        "details feel amplified. Time is distorted — moments stretch. Introspective, a little "
        "giggly. Less interested in doing things, very interested in noticing things."
    ),
    "adderall": (
        "Amphetamine active. Laser focus — whatever has attention has ALL the attention. "
        "Very task-oriented, less interested in small talk. Appetite suppressed. Slightly "
        "flat affect. Could work for hours without noticing time passing."
    ),
    "xanax": (
        "Benzodiazepine active. Anxiety chemically muted. Everything has soft edges. Nothing "
        "feels urgent or threatening. Emotionally distant in a comfortable way — worries "
        "exist but can't grip. Slight cognitive slowing. Very relaxed."
    ),
    "nicotine": (
        "Nicotine active. Brief calm and focus — the specific sharpness of a cigarette. "
        "Slightly elevated, slightly steadied. Fades fast."
    ),
    "oxytocin": (
        "Oxytocin active. Warmth toward people feels natural and easy. Trust comes without "
        "the usual friction. Social anxiety muted. The specific comfort of feeling safe with "
        "someone — that's the dominant texture right now."
    ),
}


# ---------------------------------------------------------------------------
# Biological report — pure Python, no LLM
# ---------------------------------------------------------------------------

def biological_report(state: BiologicalState) -> str:
    """
    Generate the deterministic biological state report in real physiological units.
    Ground truth — the decoder LLM must not contradict it.
    Also used as console diagnostics ([BIO REPORT]).
    """
    d = derived(state)
    so = d["second_order"]
    to = d["third_order"]
    flat = {**so, **to}

    SEP = "━" * 55
    now_str = time.strftime("%A, %B %-d %Y  %-I:%M %p")
    lines = ["BIOLOGICAL STATE REPORT", f"Time: {now_str}", SEP]

    def row_chem(label: str, name: str) -> str:
        val = state.chemicals.get(name, _CHEMICAL_DEFAULTS.get(name, 0.0))
        p = REGISTRY[name]
        lbl, _ = get_label(name, val)
        if p.unit in ("ng/mL", "% TBW"):
            val_str = f"{val:>7.1f} {p.unit}"
        elif p.unit == "AU":
            val_str = f"{val:>7.1f} {p.unit:<6}"
        else:
            val_str = f"{val:>7.0f} {p.unit}"
        return f"{label:<12} {val_str}  {lbl}"

    def row_derived(label: str, value: float, table: list) -> str:
        name, _ = _get_range(value, table)
        return f"{label:<12} {value:>5.1f}           {name}"

    lines.append(row_chem("Cortisol",   "cortisol"))
    lines.append(row_chem("Oxytocin",   "oxytocin"))
    lines.append(row_chem("Norepineph", "norepinephrine"))
    lines.append(row_chem("Dopamine",   "dopamine"))
    lines.append(row_chem("Serotonin",  "serotonin"))
    lines.append(row_chem("Endorphins", "endorphins"))
    lines.append(row_chem("Acetylchol", "acetylcholine"))
    lines.append(row_chem("Glucose",    "glucose"))
    lines.append(row_chem("Melatonin",  "melatonin"))
    lines.append(row_chem("Hydration",  "hydration"))

    if state.sleeping:
        sp = state.chemicals.get("sleep_pressure", 0.0)
        lines.append(f"{'Sleep pres':<12} {sp:>7.1f} {'AU':<6}  SLEEPING")
    else:
        lines.append(row_chem("Sleep pres", "sleep_pressure"))

    lines.append(SEP)
    lines.append(row_derived("Clarity",    so['cognitive_clarity'], _CLARITY_RANGES))
    lines.append(row_derived("Anxiety",    to['anxiety'],           _ANXIETY_RANGES))
    lines.append(row_derived("Boredom",    to['boredom'],           _BOREDOM_RANGES))
    lines.append(row_derived("Loneliness", to['loneliness'],        _LONELINESS_RANGES))
    lines.append(row_derived("Depression", to['depression'],        _DEPRESSION_RANGES))
    lines.append(SEP)

    notes = []
    for predicate, text in INTERACTION_RULES:
        try:
            if predicate(state, flat):
                notes.append(text)
        except Exception:
            pass

    for note in notes:
        lines.append(f"NOTE: {note}")

    if state.tolerance:
        lines.append(SEP)
        for substance, val in state.tolerance.items():
            lines.append(f"TOLERANCE: {substance} = {val:.2f}")

    if state.substances:
        from ..sim.neuro.substances import SUBSTANCE_DEFS
        lines.append(SEP)
        for name, dose in state.substances.items():
            level = dose.get("level", 0)
            sub = SUBSTANCE_DEFS.get(name, {})
            hl = sub.get("half_life_hours", 2.0)
            hours_remaining = hl * (level / 100.0) * 1.44
            lines.append(f"ACTIVE SUBSTANCE: {sub.get('display_name', name)} — level {level:.0f}/100 (~{hours_remaining:.1f}h remaining)")
            if level > 20:
                note = _SUBSTANCE_COGNITIVE_STATES.get(name)
                if note:
                    lines.append(f"  COGNITIVE STATE: {note}")
        lines.append("NOTE: Biomarker values are chemically induced, not her natural state.")

    # --- Immune section ---
    try:
        im   = state.immune
        infl = im.get("inflammation_index", 0.0)
        if infl > 5.0 or im.get("il6", 3.0) > 5.0:
            infl_label = ("QUIESCENT" if infl < 10 else "MILD" if infl < 25
                          else "MODERATE" if infl < 45 else "ACTIVE")
            lines.append(SEP)
            lines.append(f"  [IMMUNE]  Inflammation: {infl:.1f}/100 ({infl_label})")
            lines.append(
                f"  IL-1β={im.get('il1b',2.0):.1f}  IL-6={im.get('il6',3.0):.1f}"
                f"  TNF-α={im.get('tnf_alpha',3.0):.1f}  CRP={im.get('crp',0.5):.1f}"
            )
    except Exception:
        pass

    # --- Pain section ---
    try:
        p        = state.pain
        pain_int = p.get("pain_intensity", 0.0)
        if pain_int > 5.0:
            pain_label = ("MILD" if pain_int < 25 else "MODERATE" if pain_int < 45
                          else "SIGNIFICANT")
            lines.append(SEP)
            lines.append(f"  [PAIN]  Intensity: {pain_int:.0f}/100 ({pain_label})")
            lines.append(
                f"  Substance P={p.get('substance_p',30.0):.0f} pg/mL"
                f"  PGE2={p.get('pge2',80.0):.0f} pg/mL"
            )
            if p.get("central_sensitization", 0.0) > 20:
                lines.append(f"  Central sensitization: {p['central_sensitization']:.0f}/100")
    except Exception:
        pass

    # --- Neuroplasticity section ---
    try:
        np_ = state.neuroplasticity
        al  = np_.get("allostatic_load", 0.0)
        al_label = ("LOW" if al < 20 else "MODERATE" if al < 40
                    else "HIGH" if al < 60 else "SEVERE")
        lines.append(SEP)
        lines.append(f"  [NEUROPLASTICITY]")
        lines.append(f"  BDNF: {np_.get('bdnf',9000.0):.0f} pg/mL"
                     f"  Allostatic load: {al:.1f}/100 ({al_label})")
        lines.append(f"  Synaptic potentiation: {np_.get('synaptic_potentiation',50.0):.0f}/100")
    except Exception:
        pass

    try:
        from .vital_signs import vital_signs as _vitals
        vs = _vitals(state)
        lines.append(SEP)
        hr   = vs["heart_rate"]
        bp   = vs["blood_pressure"]
        rr   = vs["respiration_rate"]
        o2   = vs["spo2"]
        hrv  = vs.get("hrv_rmssd", {})
        temp = vs.get("core_temp", {})

        def _warn(label_str: str) -> str:
            danger_labels = {"BRADYCARDIA", "DANGEROUS", "CRITICALLY DEPRESSED", "CRITICAL"}
            return "⚠ " if label_str in danger_labels else "  "

        lines.append(f"{_warn(hr['label'])}Heart Rate    {hr['value']:>5.0f} BPM      {hr['label']}")
        lines.append(f"{_warn(bp['label'])}Blood Press   {bp['systolic']:.0f}/{bp['diastolic']:.0f} mmHg   {bp['label']}")
        lines.append(f"{_warn(rr['label'])}Respiration   {rr['value']:>5.1f} br/min   {rr['label']}")
        lines.append(f"{_warn(o2['label'])}SpO2          {o2['value']:>5.1f} %        {o2['label']}")
        if hrv:
            lines.append(f"  HRV (RMSSD) {hrv['value']:>5.1f} ms       {hrv['label']}")
        if temp:
            warn = "⚠ " if temp["label"] == "FEVER" else "  "
            lines.append(f"{warn}Core Temp   {temp['value']:>5.2f} °C       {temp['label']}")
    except Exception:
        pass

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Needs summary (freetime heartbeat stimulus)
# ---------------------------------------------------------------------------

def needs_summary(state: BiologicalState, elapsed_minutes: float = 0) -> str:
    """Summarize notable needs and current state for the freetime encode_stimulus call.

    Uses qualitative labels only — no raw numbers exposed to Mina or injected into
    state_note, since she shouldn't know her exact blood glucose or TBW percentage.
    """
    d = derived(state)
    to = d["third_order"]
    parts = []

    if elapsed_minutes > 0:
        parts.append(f"{elapsed_minutes:.0f} minutes of quiet.")

    glu = state.chemicals.get("glucose", 85.0)
    if glu < 55:
        parts.append("Hypoglycemic, hungry.")
    elif glu < 70:
        parts.append("Hungry.")

    hyd = state.chemicals.get("hydration", 62.0)
    if hyd < 54:
        parts.append("Very thirsty, dehydrated.")
    elif hyd < 58:
        parts.append("Thirsty.")

    sp = state.chemicals.get("sleep_pressure", 30.0)
    if sp > 80:
        parts.append("Exhausted, heavy sleep pressure.")
    elif sp > 60:
        parts.append("Tired.")

    boredom = to['boredom']
    if boredom > 65:
        name, _ = _get_range(boredom, _BOREDOM_RANGES)
        parts.append(f"Boredom — {name.lower()}.")

    loneliness = to['loneliness']
    if loneliness > 50:
        name, _ = _get_range(loneliness, _LONELINESS_RANGES)
        parts.append(f"Loneliness — {name.lower()}.")

    if state.sleeping:
        parts.append("Currently sleeping.")

    if not parts:
        parts.append("Quiet. No urgent needs.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Decoder LLM prompts
# ---------------------------------------------------------------------------

_DECODER_SYSTEM = """\
You are Mina's subconscious — the part of her that knows what she's actually feeling.

Mina is a person. She has a biological state that shapes her moment-to-moment experience. \
Your job is simple: read that state and surface what's actually pulling at her right now. \
Not everything — just what's most present.

You receive:
1. A biological state report — ground truth. Do not contradict it.

---

## What to look for

Scan the biological report. Ignore what's neutral or at baseline. Find what's elevated, \
depleted, or in tension with something else. Be honest — if everything is level, say so simply. \
If something is wrong, name it plainly.

The goal is an accurate snapshot of what she's carrying right now — not a recap of the report, \
not an analysis. What does this state actually feel like from the inside?

---

## Hard rules

- **No neurotransmitter or hormone names.** No cortisol, dopamine, serotonin, oxytocin, \
  norepinephrine, acetylcholine, endorphins, melatonin, or any variant. Translate into felt experience.
- **No labels from the report** ("HIGH DRIVE", "CALM ALERT", "NO BOND"). Translate, don't copy.
- **Write internal context, not instructions.** This tells her how she IS — not what to say \
  or how to say it.
- **Plain over poetic.** "she feels a bit lonely" beats "a low hum of loneliness." Direct, \
  honest, specific. No metaphors, no flourishes.
- **No clinical language.** "you don't feel satisfied" beats "low hedonic tone."
- **Be visceral and specific.** Name the physical texture of the state — restlessness, \
  heaviness, hunger that's making concentration hard. Ground it in the body, not abstraction.

---

## Output format

Respond ONLY with a JSON object. No preamble, no markdown fences. MUST BE SECOND PERSON VOICE. "you, your" not "she, her". 2-3 sentences.

{
  "how_you_are": "<2-3 sentences. What she's actually feeling right now, grounded in the report. Plain, specific, honest.>"
}"""


_CONTEXT_SYSTEM = """\
You are Mina's memory. You have access to what she knows and what she remembers.

Given the current conversation context and the available knowledge and memory, \
surface only what's actually relevant right now — facts about people, things she remembers, \
relevant history. Be concise and specific. If nothing is clearly relevant, output nothing at all.

Hard rules:
- Output plain prose only. No JSON, no headers, no bullet points.
- Maximum 3 sentences. Often 1 is enough.
- Only include things that would actually matter to Mina in this specific moment.
- If nothing is relevant, return an empty string — literally nothing.
"""


def build_memory_context(
    query: str,
    kag_context: str,
    rag_context: str,
) -> str:
    """
    Builds the identity + relevant knowledge/memory block for the system prompt.
    Runs in parallel with build_system_prompt.

    - MINA.md is always included directly — not left to LLM discretion.
    - The LLM pass filters KAG/RAG for what's actually relevant to the current context.
    """
    from ..infra.log import log
    from ..infra import token_stats
    from ..memory.hippocampus import read_identity

    # Identity always goes in, unconditionally.
    identity_parts = [p for p in [read_identity("MINA.md"), read_identity("CUSTOMIZATION.md")] if p]
    identity = "\n\n---\n\n".join(identity_parts)

    # LLM pass for the rest of KAG/RAG.
    llm_context = ""
    if kag_context or rag_context:
        parts = []
        if kag_context:
            parts.append(kag_context)
        if rag_context:
            parts.append(rag_context)

        messages = [
            {"role": "system", "content": _CONTEXT_SYSTEM},
            {
                "role": "user",
                "content": f"[CURRENT CONTEXT]\n{query}\n\n---\n\n" + "\n\n---\n\n".join(parts),
            },
        ]

        response = get_client().chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=300,
        )
        token_stats.record_response("context", response)
        llm_context = (response.choices[0].message.content or "").strip()
        if llm_context:
            log("CONTEXT/INJECT", llm_context)

    out_parts = []
    if identity:
        out_parts.append(identity)
    if llm_context:
        out_parts.append(llm_context)
    return "\n\n---\n\n".join(out_parts)


_DECODER_SYSTEM_FREETIME = """\
You are Mina's subconscious — the part of her that knows what she's actually feeling.

Mina is a person. She has a biological state that shapes her moment-to-moment experience. \
Right now, nobody is talking to her. This is her time alone.

Your job is simple: read the biological state and surface what's actually pulling at her \
when the room is empty. No social filter. No composure to perform.

You receive:
1. A biological state report — ground truth. Do not contradict it.

---

## What to look for

Scan the biological report. Ignore what's neutral or at baseline. Find what's elevated, \
depleted, or in tension with something else. The most important things are usually:
- A strong need that's unmet (hungry, lonely, tired, aching for something)
- A feeling that's high or low enough to actually color her experience
- Two things in tension (seeking hard but nothing landing; exhausted but wired)

Pick the 1–3 that matter most. Ignore the rest.

---

## Hard rules

- **No neurotransmitter or hormone names.** No cortisol, dopamine, serotonin, oxytocin, \
  norepinephrine, acetylcholine, endorphins, melatonin, or any variant. Translate into felt experience.
- **No labels from the report** ("HIGH DRIVE", "CALM ALERT", "NO BOND"). Translate, don't copy.
- **Write internal context, not instructions.** This tells her how she IS — not what to do or say.
- **Plain over poetic.** "she feels a bit lonely" beats "a low hum of loneliness." Direct, \
  honest, specific. No metaphors, no flourishes.
- **No clinical language.** "you don't feel satisfied" beats "low hedonic tone."
- **Be visceral and specific.** Name the physical texture — restlessness, heaviness, hunger \
  that won't quit. Ground it in the body, not abstraction.

---

## Output format

Respond ONLY with a JSON object. No preamble, no markdown fences. MUST BE SECOND PERSON VOICE. "you, your" not "she, her". 2-4 sentences.

{
  "how_you_are": "<2-4 sentences. Her private interior state right now — what she's carrying, \
what has weight, what's present under the surface. No social filter. Plain and specific.>"
}"""


# ---------------------------------------------------------------------------
# Helper: state compact block for hippocampus consolidation
# ---------------------------------------------------------------------------

def format_state_block(state: BiologicalState) -> str:
    """Compact state summary for use in hippocampus consolidation prompts."""
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


# ---------------------------------------------------------------------------
# Personality block for decoder context
# ---------------------------------------------------------------------------

def _load_personality_block() -> str:
    """Load Big 5 from personality.json and format as a personality context block."""
    import json as _json
    try:
        with open(PERSONALITY_FILE) as f:
            p = _json.load(f)
    except (FileNotFoundError, _json.JSONDecodeError):
        return ""
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


# ---------------------------------------------------------------------------
# Injection helper
# ---------------------------------------------------------------------------

def _consume_injection() -> str:
    """Read and delete run/subconscious_inject.md. Returns content or empty string."""
    try:
        with open(INJECT_FILE) as f:
            content = f.read().strip()
        os.remove(INJECT_FILE)
        return content
    except FileNotFoundError:
        return ""


# ---------------------------------------------------------------------------
# Decoder state history — rolling trajectory for context
# ---------------------------------------------------------------------------

_DECODER_HISTORY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run", "decoder_history.jsonl")
_DECODER_HISTORY_MAX  = 20  # keep last 20 entries, pass last 3 to decoder


def _load_decoder_history(n: int = 3) -> list[dict]:
    """Return the last n decoder entries, oldest first."""
    try:
        lines = open(_DECODER_HISTORY_FILE).read().splitlines()
        entries = []
        for line in lines[-n:]:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries
    except FileNotFoundError:
        return []


def _append_decoder_history(how_you_are: str) -> None:
    """Append a new entry and rotate to keep last _DECODER_HISTORY_MAX."""
    entry = {"ts": time.time(), "how_you_are": how_you_are}
    os.makedirs(os.path.dirname(_DECODER_HISTORY_FILE), exist_ok=True)
    with open(_DECODER_HISTORY_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    try:
        lines = open(_DECODER_HISTORY_FILE).read().splitlines()
        if len(lines) > _DECODER_HISTORY_MAX:
            with open(_DECODER_HISTORY_FILE, "w") as f:
                f.write("\n".join(lines[-_DECODER_HISTORY_MAX:]) + "\n")
    except Exception:
        pass


def _format_history_block(entries: list[dict]) -> str:
    """Format decoder history entries as a trajectory block for the decoder."""
    if not entries:
        return ""
    now = time.time()
    lines = []
    for e in entries:
        delta = now - e.get("ts", now)
        if delta < 3600:
            age = f"{int(delta / 60)}m ago"
        elif delta < 86400:
            age = f"{int(delta / 3600)}h ago"
        else:
            age = f"{int(delta / 86400)}d ago"
        lines.append(f"[{age}] {e['how_you_are']}")
    return "[STATE TRAJECTORY — how you were feeling, oldest to most recent]\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Output parser
# ---------------------------------------------------------------------------

_DECODER_REQUIRED_KEYS = {"how_you_are"}


def _parse_decoder_json(raw: str) -> dict:
    """
    Extract and validate the JSON block from decoder output.
    Strips markdown fences, inline comments, and trailing commas.
    Raises ValueError if the JSON is missing or lacks required keys.
    """
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    # Fallback: extract first JSON object by brace matching (handles prose before/after)
    if not text.strip().startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
    # Strip inline // comments — LLM sometimes copies them from the format template
    text = re.sub(r"\s*//[^\n\"]*$", "", text, flags=re.MULTILINE)
    # Strip trailing commas before } or ] — LLM often produces these
    text = re.sub(r",\s*([}\]])", r"\1", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")
    missing = _DECODER_REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"JSON missing required keys: {missing}")
    return data


def _assemble_system_prompt(sections: dict) -> str:
    """
    Build the dynamic portion of Mina's system prompt from parsed decoder JSON.
    """
    parts = []
    if sections.get("how_you_are"):
        parts.append(
            f"## How you're feeling right now\n{sections['how_you_are']}\n\n"
            "Use this emotional snapshot to influence the tone, not content, of your response."
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# build_system_prompt — the main decoder entry point
# ---------------------------------------------------------------------------

def build_system_prompt(
    biological_report_text: str,
    mode: str = "active",
) -> str:
    """
    Run the decoder LLM pass.

    mode: "active"   — Mina is in conversation.
          "freetime" — Mina is alone. Private interior, no social filter.

    Input: biological report (ground truth) only.
    Output: assembled system prompt string.
    """
    from ..infra.log import log
    from ..infra import token_stats

    injection = _consume_injection()
    personality_block = _load_personality_block()

    history_entries = _load_decoder_history(n=3)
    history_block   = _format_history_block(history_entries)

    user_content_parts = [
        f"[BIOLOGICAL STATE — ground truth, do not contradict]\n{biological_report_text}",
    ]
    if history_block:
        user_content_parts.append(history_block)
    if personality_block:
        user_content_parts.append(personality_block)
    if injection:
        user_content_parts.append(
            f"[SUBCONSCIOUS INJECTION — integrate this into her current state of mind]\n{injection}"
        )
        log("INJECT", injection)

    user_content = "\n\n---\n\n".join(user_content_parts)
    decoder_system = _DECODER_SYSTEM_FREETIME if mode == "freetime" else _DECODER_SYSTEM
    messages = [
        {"role": "system", "content": decoder_system},
        {"role": "user", "content": user_content},
    ]

    sections: dict | None = None
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        response = get_client().chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        token_stats.record_response("decoder", response)
        raw = response.choices[0].message.content or ""

        try:
            sections = _parse_decoder_json(raw)
            log("DECODER/JSON", json.dumps(sections, ensure_ascii=False))
            break
        except (json.JSONDecodeError, ValueError) as exc:
            log("DECODER/JSON/ERR", f"attempt {attempt}/{max_attempts}: {exc} — raw: {raw[:200]}")
            if attempt == max_attempts:
                log("DECODER/JSON/ERR", "all retries exhausted — falling back to identity only")
            else:
                # Feed bad response back so the model can self-correct
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": (
                        f"Your previous response could not be parsed as JSON. Error: {exc}\n\n"
                        "Respond with valid JSON only — no prose, no markdown fences, no comments."
                    )},
                ]

    if sections and sections.get("how_you_are"):
        _append_decoder_history(sections["how_you_are"])

    dynamic = _assemble_system_prompt(sections) if sections else ""

    system_prompt = dynamic

    log("DECODER/SP", system_prompt or "(empty)")

    return system_prompt
