"""
Biological state report — pure Python, no LLM.
Formats state in real physiological units for logging and as input to LLM calls.
"""
import time

from src.brain.brainstem.state import BiologicalState, derived, _CHEMICAL_DEFAULTS
from src.engine.chem.registry import REGISTRY
from src.engine.chem.units import get_label
from src.engine.rules import COMPOUND_RULES

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


def _get_range(value: float, table: list) -> tuple[str, str]:
    for upper, name, impl in table:
        if value < upper:
            return name, impl
    return table[-1][1], table[-1][2]


def biological_report(state: BiologicalState) -> str:
    """
    Generate the deterministic biological state report in real physiological units.
    Ground truth — LLM calls must not contradict it.
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
    for chem_name, chem_profile in REGISTRY.items():
        if not chem_profile.notes:
            continue
        val = state.chemicals.get(chem_name, _CHEMICAL_DEFAULTS.get(chem_name, 0.0))
        for threshold, _tag, description in chem_profile.notes:
            if val >= threshold:
                notes.append(description)

    concentrations = {k: state.chemicals.get(k, _CHEMICAL_DEFAULTS.get(k, 0.0))
                      for k in _CHEMICAL_DEFAULTS}
    derived_with_extras = dict(flat)
    derived_with_extras["sleeping"] = state.sleeping
    derived_with_extras["hedonic_setpoint"] = state.body.get("hedonic_setpoint", 15.0)
    for rule in COMPOUND_RULES:
        try:
            if rule.condition(concentrations, derived_with_extras):
                notes.append(rule.description)
        except Exception:
            pass

    for note in notes:
        lines.append(f"NOTE: {note}")

    if state.tolerance:
        lines.append(SEP)
        for substance, val in state.tolerance.items():
            lines.append(f"TOLERANCE: {substance} = {val:.2f}")

    if state.substances:
        from src.engine.neuro.substances import SUBSTANCE_DEFS
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
        from src.brain.brainstem.vital_signs import vital_signs as _vitals
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


def needs_summary(state: BiologicalState, elapsed_minutes: float = 0) -> str:
    """Qualitative needs summary for freetime encode_stimulus. No raw numbers exposed."""
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


def format_state_block(state: BiologicalState) -> str:
    """Compact state summary for hippocampus consolidation prompts."""
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
