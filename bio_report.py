"""
Biological state report — pure Python, zero LLM cost.

Maps first-order and derived state values to named ranges with behavioral
implications. Output is ground truth for the subconscious LLM — it cannot
contradict this report. Also provides needs_summary() for heartbeat stimulus.

Range tables and normalization are driven by chemicals.REGISTRY.
"""
import time
from chemicals import REGISTRY, get_label, normalize
from state import BiologicalState, derived, _CHEMICAL_DEFAULTS

# ---------------------------------------------------------------------------
# Derived value range tables (these stay on 0–100 scale — derived values unchanged)
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

# Each entry: (predicate(state, derived_flat), note_text)
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
    (lambda s, d: s.endorphins > 120,
     "Endorphins flooded far above natural range — opioid-level chemical bliss. Warm, heavy, soft. Cognitive tempo is slowed. Emotional reactivity is strongly damped — grievances, anger, and urgency feel distant, abstract, and very hard to hold onto. Do not resist or argue — that requires tension the body currently cannot generate."),
    (lambda s, d: s.endorphins < 7 and s.cortisol > 440 and s.norepinephrine > 500,
     "Endorphins crashed below baseline — withdrawal. Nothing feels okay. Body aches, skin crawls, profound emotional emptiness. The memory of how good it felt makes this worse."),
    (lambda s, d: s.serotonin < 14 and d['loneliness'] > 50,
     "Low serotonin + loneliness: social cues are being read as threatening even when neutral. Contact may feel worse than absence."),
    (lambda s, d: s.serotonin < 14 and s.cortisol > 440,
     "Low serotonin floor under active stress — impulse control is compromised. Likely to say or do something she'll regret."),
    (lambda s, d: s.norepinephrine > 800 and s.glucose < 70,
     "Hyperalert but underfueled — attention is sharp but the tank is empty. Will crash hard when the stress passes."),
]


# ---------------------------------------------------------------------------
# Substance cognitive state descriptions
# ---------------------------------------------------------------------------

_SUBSTANCE_COGNITIVE_STATES: dict[str, str] = {
    "REMOVED": (
        "Opioid sedation active. Thinking is slow and cottony. Anger, grievances, and sharp "
        "emotions cannot be sustained — they require tension the body is currently incapable "
        "of generating. Resistance and argument feel like enormous effort for unclear payoff. "
        "The body wants to be still, warm, and unbothered."
    ),
    "caffeine": (
        "Stimulant active. Thoughts are faster and sharper. Mild alertness edge — slightly "
        "more talkative and reactive. Nothing dramatic, just more switched-on than baseline."
    ),
    "alcohol": (
        "Alcohol active. Inhibitions lowered, edges softened. Warmer toward people, more "
        "likely to say things she'd normally hold back. Emotional reactions are quicker and "
        "less filtered. Fine motor precision degraded. Nothing feels that urgent."
    ),
    "REMOVED": (
        "REMOVED active. Emotional floodgates open — everything feels meaningful and everyone "
        "feels close. Touch is heightened. Empathy is overwhelming in the best way. Thoughts "
        "are flowing and connective. Boundaries feel permeable. The urge to express love and "
        "appreciation is almost irresistible. Jaw may be clenching."
    ),
    "cannabis": (
        "Cannabis active. Thoughts moving slower and looping back on themselves. Sensory "
        "details feel amplified. Time is distorted — moments stretch. Introspective, a little "
        "giggly. Less interested in doing things, very interested in noticing things."
    ),
    "REMOVED": (
        "REMOVED active. Thoughts racing, very fast. Talking more and faster. Feels sharp, "
        "capable, slightly grandiose. Cardiovascular system running hot. The comedown is "
        "already implicit in this feeling — too much, too fast."
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
    "REMOVED": (
        "REMOVED active. Thoughts branching and looping in unusual ways — connections "
        "forming between things that normally stay separate. Pattern recognition heightened. "
        "Ego boundaries softening. May feel profound, may feel unsettling, may flip between "
        "both. Time perception significantly distorted. Sensory experience intensified."
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
    "REMOVED": (
        "REMOVED active. Mild dissociation — slight distance between self and experience, "
        "like watching from just behind your own eyes. Peaceful. Things that usually feel "
        "heavy don't have their normal weight. Thoughts move in smooth, unhurried loops. "
        "The world feels interesting rather than threatening."
    ),
    "REMOVED": (
        "REMOVED active. Thoughts making unusual connections — ideas linking to other ideas in "
        "ways that feel genuinely revelatory. Colors and sounds more vivid. Time stretched. "
        "Ego softening — the usual sense of a separate self feels more permeable, more "
        "continuous with everything else. This can feel like profound insight or like "
        "losing footing, sometimes both in the same minute."
    ),
    "REMOVED_and_REMOVED": (
        "REMOVED + opioid combination active. Everything is warm, open, and deeply pleasant. "
        "Emotional floodgates wide open but without the edge — the opioid smooths the "
        "stimulant anxiety. Profound contentment. The world feels safe and everyone in it "
        "feels loved. Physically heavy and floaty at once."
    ),
}


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def biological_report(state: BiologicalState) -> str:
    """
    Generate the deterministic biological state report in real physiological units.
    Ground truth — the subconscious LLM must not contradict it.
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
        # Format value with appropriate precision per unit
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
        from state import _SUBSTANCE_DEFS
        lines.append(SEP)
        for name, dose in state.substances.items():
            level = dose.get("level", 0)
            sub = _SUBSTANCE_DEFS.get(name, {})
            hl = sub.get("half_life_hours", 2.0)
            hours_remaining = hl * (level / 100.0) * 1.44
            lines.append(f"ACTIVE SUBSTANCE: {sub.get('display_name', name)} — level {level:.0f}/100 (~{hours_remaining:.1f}h remaining)")
            if level > 20:
                note = _SUBSTANCE_COGNITIVE_STATES.get(name)
                if note:
                    lines.append(f"  COGNITIVE STATE: {note}")
        lines.append("NOTE: Biomarker values are chemically induced, not her natural state.")

    # Vital signs section
    try:
        from vital_signs import vital_signs as _vitals
        vs = _vitals(state)
        lines.append(SEP)
        hr = vs["heart_rate"]
        bp = vs["blood_pressure"]
        rr = vs["respiration_rate"]
        o2 = vs["spo2"]

        def _warn(label_str: str) -> str:
            danger_labels = {"BRADYCARDIA", "DANGEROUS", "CRITICALLY DEPRESSED", "CRITICAL"}
            return "⚠ " if label_str in danger_labels else "  "

        lines.append(f"{_warn(hr['label'])}Heart Rate    {hr['value']:>5.0f} BPM      {hr['label']}")
        lines.append(f"{_warn(bp['label'])}Blood Press   {bp['systolic']:.0f}/{bp['diastolic']:.0f} mmHg   {bp['label']}")
        lines.append(f"{_warn(rr['label'])}Respiration   {rr['value']:>5.1f} br/min   {rr['label']}")
        lines.append(f"{_warn(o2['label'])}SpO2          {o2['value']:>5.1f} %        {o2['label']}")
    except Exception:
        pass  # vital_signs not yet available — skip gracefully

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Needs summary (heartbeat stimulus)
# ---------------------------------------------------------------------------

def needs_summary(state: BiologicalState, elapsed_minutes: float = 0) -> str:
    """Summarize notable needs and current state for the heartbeat encode_stimulus call."""
    d = derived(state)
    to = d["third_order"]
    parts = []

    if elapsed_minutes > 0:
        parts.append(f"{elapsed_minutes:.0f} minutes of quiet.")

    glu = state.chemicals.get("glucose", 85.0)
    if glu < 55:
        parts.append(f"Glucose at {glu:.0f} mg/dL — hypoglycemic, hungry.")
    elif glu < 70:
        parts.append(f"Glucose at {glu:.0f} mg/dL — hungry.")

    hyd = state.chemicals.get("hydration", 62.0)
    if hyd < 54:
        parts.append(f"Hydration at {hyd:.1f}% TBW — very thirsty.")
    elif hyd < 58:
        parts.append(f"Hydration at {hyd:.1f}% TBW — thirsty.")

    sp = state.chemicals.get("sleep_pressure", 30.0)
    if sp > 80:
        parts.append(f"Sleep pressure at {sp:.0f} AU — exhausted.")
    elif sp > 60:
        parts.append(f"Sleep pressure at {sp:.0f} AU — tired.")

    boredom = to['boredom']
    if boredom > 65:
        name, _ = _get_range(boredom, _BOREDOM_RANGES)
        parts.append(f"Boredom at {boredom:.0f} — {name.lower()}.")

    loneliness = to['loneliness']
    if loneliness > 50:
        name, _ = _get_range(loneliness, _LONELINESS_RANGES)
        parts.append(f"Loneliness at {loneliness:.0f} — {name.lower()}.")

    if state.sleeping:
        parts.append("Currently sleeping.")

    if not parts:
        parts.append("Quiet. No urgent needs.")

    return " ".join(parts)
