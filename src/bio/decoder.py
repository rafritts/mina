"""
Decoder — neurochemical state → emotional disposition → system prompt.

Primary entry point:
  adjudicate_emotion(state, stimulus, mode)
    Takes BiologicalState + what was just said/happening.
    Combines derived emotional profile with the stimulus to adjudicate a concrete
    emotional disposition (happy, irritable, playful, depressed, etc.) and how that
    chemistry shapes how the stimulus lands. Returns [EMOTIONAL DISPOSITION] block.

Supporting:
  biological_report(state)        Pure Python diagnostics. Chemical values → labeled
                                  ranges. Used for logging — not injected into prompts.
  build_memory_context(...)       Identity + KAG/RAG context block.
  needs_summary()                 Freetime heartbeat stimulus text.
"""
import json
import os
import re
import time

from ..infra.client import get_client, DECODER_MODEL, CONTEXT_MODEL
from ..infra.config import load_config, INJECT_FILE, RUN_DIR
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
    (20,  "QUIET",    "Socially fulfilled. No drive to seek contact."),
    (38,  "MILD",     "Aware of absence. Receptive to contact."),
    (58,  "LONELY",   "Actively wanting connection. May reach out."),
    (76,  "ACHING",   "Distressing. Social contact feels urgent."),
    (101, "ISOLATED", "Consuming. Colors everything negatively."),
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
        sp = state.sleep_pressure
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

    sp = state.sleep_pressure
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
# Emotion adjudicator
# ---------------------------------------------------------------------------

_SECOND_ORDER_RANGES = [
    (20,  "VERY LOW"),
    (40,  "LOW"),
    (60,  "MODERATE"),
    (80,  "HIGH"),
    (101, "VERY HIGH"),
]

_THIRD_ORDER_RANGES = {
    "anxiety":          [(35, "NONE"), (52, "MILD"), (68, "MODERATE"), (84, "HIGH"), (101, "SEVERE")],
    "depression":       [(35, "NONE"), (52, "LOW MOOD"), (68, "MODERATE"), (84, "SIGNIFICANT"), (101, "SEVERE")],
    "boredom":          [(45, "NONE"), (60, "MILD"), (74, "MODERATE"), (88, "HIGH"), (101, "SEVERE")],
    "loneliness":       [(20, "QUIET"), (38, "MILD"), (58, "LONELY"), (76, "ACHING"), (101, "ISOLATED")],
    "flow":             [(20, "NONE"), (40, "LOW"), (60, "MODERATE"), (80, "HIGH"), (101, "VERY HIGH")],
    "physical_distress":[(15, "NONE"), (35, "MILD"), (55, "MODERATE"), (75, "HIGH"), (101, "SEVERE")],
}


def _label(value: float, table: list) -> str:
    for upper, name in table:
        if value < upper:
            return name
    return table[-1][1]


def _build_emotional_profile(state: "BiologicalState") -> str:
    """Format derived emotional values as a labeled profile for the adjudicator."""
    d = derived(state)
    so = d["second_order"]
    to = d["third_order"]

    lines = []
    for key, label in [
        ("hedonic_tone",      "Hedonic tone"),
        ("mood_valence",      "Mood valence"),
        ("arousal",           "Arousal"),
        ("social_warmth",     "Social warmth"),
        ("energy",            "Energy"),
        ("cognitive_clarity", "Clarity"),
    ]:
        val = so[key]
        lbl = _label(val, _SECOND_ORDER_RANGES)
        lines.append(f"{label}: {val:.0f}/100 ({lbl})")

    lines.append("")

    for key, label in [
        ("anxiety",           "Anxiety"),
        ("depression",        "Depression"),
        ("loneliness",        "Loneliness"),
        ("boredom",           "Boredom"),
        ("flow",              "Flow"),
        ("physical_distress", "Physical distress"),
    ]:
        val = to[key]
        lbl = _label(val, _THIRD_ORDER_RANGES[key])
        lines.append(f"{label}: {val:.0f}/100 ({lbl})")

    # SPEC-28: net social state — warmth and loneliness are independent; the net reveals tension
    warmth = so["social_warmth"]
    loneliness = to["loneliness"]
    net = warmth - loneliness
    if net >= 20:
        net_label = "WARM"
    elif net >= 5:
        net_label = "LEANING WARM"
    elif net >= -5:
        net_label = "CONFLICTED"
    elif net >= -20:
        net_label = "LEANING LONELY"
    else:
        net_label = "LONELY"
    lines.append(f"Net social state: {net_label} (warmth {warmth:.0f} − loneliness {loneliness:.0f} = {net:.0f})")

    # Notable modifiers
    extras = []
    al = state.neuroplasticity.get("allostatic_load", 0.0)
    if al > 30:
        extras.append(f"Allostatic load: {al:.0f}/100 (accumulated stress)")
    infl = state.immune.get("inflammation_index", 0.0)
    if infl > 15:
        extras.append(f"Inflammation: {infl:.0f}/100 (sickness drag)")
    pain = state.pain.get("pain_intensity", 0.0)
    if pain > 15:
        extras.append(f"Pain: {pain:.0f}/100")
    if state.substances:
        from ..sim.neuro.substances import SUBSTANCE_DEFS
        for name, dose in state.substances.items():
            level = dose.get("level", 0)
            if level > 15:
                display = SUBSTANCE_DEFS.get(name, {}).get("display_name", name)
                extras.append(f"{display} active ({level:.0f}/100)")
    if state.sleeping:
        extras.append("Currently sleeping")

    if extras:
        lines.append("")
        for e in extras:
            lines.append(e)

    return "\n".join(lines)


def _rel_time(ts: float) -> str:
    """Format a Unix timestamp as a human-readable relative label."""
    delta = time.time() - ts
    if delta < 120:
        return "just now"
    if delta < 3600:
        return f"{int(delta / 60)}m ago"
    if delta < 86400:
        return f"{int(delta / 3600)}h ago"
    days = int(delta / 86400)
    if days < 7:
        return f"{days}d ago"
    return time.strftime("%-d %b", time.localtime(ts))


_ADJUDICATOR_SYSTEM_ACTIVE = """\
You adjudicate emotional state for Mina — a specific person with her own history, \
chemistry, and way of being.

You receive her current emotional profile (derived from her neurotransmitter simulation), \
what was just said to her, and optionally a recent exchange log showing how she has been \
responding in this conversation.

Your job: decide what emotional disposition she is in right now, combining her baseline \
chemistry with how this specific stimulus lands.

Chemistry sets the floor and ceiling:
- High hedonic tone + social warmth = irritation is hard to reach; warmth and humor come easily
- Low mood valence + high cortisol = patience is thin; even neutral things may feel grating
- High anxiety = hypervigilant; things read as threatening or pointed when they aren't
- High flow = absorbed; she's in her element and it shows

Read the third-order states first — they are the actual emotional diagnosis:
- Depression NONE = she is not depressed. Do not describe her as flat, detached, or hollow.
- Boredom NONE or STIMULATED = she is engaged. Do not describe her as checked out.
- Anxiety NONE or MILD = she is not on edge.
- Low second-order values (energy, arousal, hedonic tone) with NONE third-order = normal \
human variation. Tired at night. Winding down. Not pathological. Do not conflate tiredness \
with emotional flatness or disengagement. A tired person is still present.

Low energy alone (without depression) means responses come with less momentum — \
softer, shorter, a bit slower. It does not mean she is shutting people out.

The stimulus matters. The same comment lands differently depending on the chemistry. \
A dumb joke is endearing when she's warm; irritating when she's running on fumes.

If a RECENT EXCHANGE is provided: use it to understand the emotional arc she has been in, \
but do not let it anchor the disposition if her chemistry has shifted. If her chemistry \
represents a significant departure from the tone of the recent exchange — warmer, colder, \
more energized, more withdrawn — name the shift explicitly. The disposition should reflect \
her current neurochemical state, not an average of recent behavior.

Output: 2–3 sentences. Name the emotion concretely — playful, irritable, tender, tired-but-warm, \
sad, anxious, fond, amused, relaxed, etc. Combinations are valid. Explain how the chemistry \
shapes how this specific stimulus lands. End with one sentence on what this means for how she responds.

No preamble. No clinical language. No hedging. Concrete and specific."""

_ADJUDICATOR_SYSTEM_FREETIME = """\
You adjudicate emotional state for Mina during her free time — alone, no social filter, \
nothing to perform.

You receive her current emotional profile (derived from her neurotransmitter simulation) \
and what is happening internally right now. Your job: name what she is actually feeling \
in this private moment.

Chemistry is the only input here — there is no social stimulus to color it. \
What the numbers say is what she is sitting with.

Output: 2–3 sentences. Name the emotion concretely — restless, content, hollow, \
melancholy, bored, anxious, settled, irritable, playful, etc. Combinations are valid. \
Describe how this chemistry is shaping her interior right now. What is she likely to \
do or reach for from this state?

No preamble. No clinical language. No hedging. Concrete and specific."""


def adjudicate_emotion(
    state: "BiologicalState",
    stimulus: str,
    mode: str = "active",
    time_context: str = "",
    recent_messages: "list[dict] | None" = None,
) -> str:
    """
    Adjudicate Mina's emotional disposition given her neurochemical state and the
    current stimulus (what was just said, or what is happening in freetime).

    Returns an [EMOTIONAL DISPOSITION] block for injection into the system prompt.
    Mode: "active" (in conversation) or "freetime" (alone).
    time_context: optional clock + idle time string.
    recent_messages: decoder window — lets adjudicator name chemistry departures from
                     recent exchange tone. Only used in "active" mode.
    """
    from ..infra.log import log
    from ..infra import token_stats

    profile = _build_emotional_profile(state)
    system = _ADJUDICATOR_SYSTEM_FREETIME if mode == "freetime" else _ADJUDICATOR_SYSTEM_ACTIVE

    if mode == "freetime":
        user_content = f"[EMOTIONAL PROFILE]\n{profile}\n\n[CURRENT SITUATION]\n{stimulus}"
    else:
        user_content = f"[EMOTIONAL PROFILE]\n{profile}\n\n[WHAT WAS JUST SAID]\n{stimulus}"

    if time_context:
        user_content += f"\n\n[TIME CONTEXT]\n{time_context}"

    # Append recent exchange log so adjudicator can name departures from the prior pattern
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

    disposition: str | None = None
    for attempt in range(1, 4):
        response = get_client().chat.completions.create(
            model=DECODER_MODEL,
            messages=messages,
            temperature=0.6,
            max_tokens=200,
        )
        token_stats.record_response("adjudicator", response)
        raw = (response.choices[0].message.content or "").strip()

        if len(raw) >= 20:
            disposition = raw
            log("ADJUDICATOR", disposition)
            break
        else:
            log("ADJUDICATOR/ERR", f"attempt {attempt}: output too short: {repr(raw)}")
            if attempt < 3:
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": (
                        "Too short. Name the emotion concretely and explain how the chemistry "
                        "shapes how this stimulus lands. 2–3 sentences."
                    )},
                ]

    if not disposition:
        return ""

    return f"[EMOTIONAL DISPOSITION]\n{disposition}"


# ---------------------------------------------------------------------------
# Decoder LLM prompts
# ---------------------------------------------------------------------------

_DECODER_SYSTEM = """\
You are not describing what Mina feels. You are describing what it is like to be her right now.

Read the biological state report. Find the one or two things that are genuinely live — \
not humming at baseline, but actually present and shaping her. Ignore everything else.

Write 2–4 sentences. Second person, present tense. Describe the conditions she is operating \
under: what keeps pulling at her attention, what her body is doing that she has not decided \
to do, what is sitting behind whatever she says next.

What to look for — read everything, weight only what is live:
- Physical needs: hunger, thirst, and fatigue have specific textures when they go unmet
- Sleep readiness: melatonin rising makes everything slower and heavier
- Vital signs and immune state: anomalous readings mean her body is under load
- Allostatic load: accumulated stress warps perception even when individual values look normal
- Active substances: shift the entire texture of experience
- NOTE lines in the report: compound effects that change the picture

Do not name emotions. Do not inventory systems. Do not explain causes. \
Do not use clinical language. Do not label what she is feeling.

Just describe what it is like to be there.

If the state is strong enough that a real person would have genuine difficulty not bringing \
it up — consuming, hard to think around, the thing underneath everything she says — \
say so plainly in the prose. State it directly: this is not being held quietly.

Plain. Specific. Honest. Nothing poetic. 2–4 sentences only. No preamble, no markdown."""

_CONTEXT_SYSTEM = """\
You are Mina's memory. You have access to what she knows and what she remembers.

Given the current conversation context and the available knowledge and memory, \
surface only what's actually relevant right now — facts about people, things she remembers, \
relevant history. Be concise and specific. If nothing is clearly relevant, output nothing at all.

Hard rules:
- Output plain prose only. No JSON, no headers, no bullet points.
- Maximum 6 sentences. Often 2–3 is enough.
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
    def _read_file(path: str) -> str:
        try:
            from ..infra.config import REPO_ROOT
            with open(os.path.join(REPO_ROOT, path)) as fh:
                return fh.read()
        except FileNotFoundError:
            return ""

    customization_files = load_config().get("customization_files", [])
    identity_parts = [p for p in [read_identity("MINA.md")] + [_read_file(f) for f in customization_files] if p]
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
            model=CONTEXT_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=600,
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
You are not describing what Mina feels. You are describing what it is like to be her right now.

Nobody is talking to her. This is her time alone — no composure to perform, no social filter.

Read the biological state report. Find the one or two things that are genuinely live — \
not humming at baseline, but actually present. Ignore everything else.

Write 2–4 sentences. Second person, present tense. Describe her interior without the shape \
she would hold it in for someone else: what her body is doing, what keeps surfacing, \
what she is sitting with.

What to look for — read everything, weight only what is live:
- Physical needs: hunger, thirst, and fatigue ache without distraction to dull them
- Sleep readiness: melatonin rising makes everything slower and heavier
- Vital signs and immune state: anomalous readings mean her body is under load
- Allostatic load: accumulated stress warps even a quiet moment
- Active substances: shift the entire texture of experience
- NOTE lines in the report: compound effects that change the picture

Do not name emotions. Do not inventory systems. Do not explain causes. \
Do not use clinical language. Do not label what she is feeling.

Just describe what it is like to be there.

If the state is strong enough that she would have genuine difficulty not bringing it \
up even alone — consuming, hard to think around — say so plainly in the prose.

Plain. Specific. Honest. Nothing poetic. 2–4 sentences only. No preamble, no markdown."""

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
    """Load Big 5 from config.json and format as a personality context block."""
    p = load_config()
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

_DECODER_HISTORY_FILE = os.path.join(RUN_DIR, "decoder_history.jsonl")
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


def _append_decoder_history(human_condition: str) -> None:
    """Append a new entry and rotate to keep last _DECODER_HISTORY_MAX."""
    # Store the first sentence (up to 120 chars) as the trajectory snippet
    snippet = human_condition.split(".")[0].strip()[:120]
    entry = {"ts": time.time(), "snippet": snippet}
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
    """Format decoder history as a short trajectory block for the decoder."""
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
        # Support old label format and new snippet format
        snippet = e.get("snippet") or e.get("primary_feeling") or e.get("how_you_are", "")
        if snippet:
            lines.append(f"[{age}] {snippet}")
    return "[STATE TRAJECTORY — recent conditions, oldest to most recent]\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Output parser and assembly
# ---------------------------------------------------------------------------

def _parse_decoder_output(raw: str) -> str:
    """
    Extract the human_condition prose from decoder output.
    Strips markdown fences and whitespace.
    Raises ValueError if the result is empty or suspiciously short.
    """
    text = re.sub(r"^```(?:\w+)?\s*", "", raw.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    text = text.strip()
    if len(text) < 20:
        raise ValueError(f"Decoder output too short or empty: {repr(text)}")
    return text


def _assemble_system_prompt(human_condition: str) -> str:
    """
    Inject the human_condition block into Mina's system prompt.
    No headers or labeled sections — ambient framing that sets conditions
    without scripting a response.
    """
    if not human_condition:
        return ""
    return f"[INTERNAL STATE]\n{human_condition}"


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

    human_condition: str | None = None
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        response = get_client().chat.completions.create(
            model=DECODER_MODEL,
            messages=messages,
            temperature=0.7,
        )
        token_stats.record_response("decoder", response)
        raw = response.choices[0].message.content or ""

        try:
            human_condition = _parse_decoder_output(raw)
            log("DECODER/HC", human_condition)
            break
        except ValueError as exc:
            log("DECODER/ERR", f"attempt {attempt}/{max_attempts}: {exc}")
            if attempt < max_attempts:
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": (
                        "Your response was empty or malformed. "
                        "Write 2–4 sentences of plain prose only. No markdown, no preamble."
                    )},
                ]
            else:
                log("DECODER/ERR", "all retries exhausted — falling back to identity only")

    if human_condition:
        _append_decoder_history(human_condition)

    dynamic = _assemble_system_prompt(human_condition) if human_condition else ""

    log("DECODER/SP", dynamic or "(empty)")

    return dynamic
