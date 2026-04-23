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

from src.application.infra.client import chat_create, DECODER_MODEL, CONTEXT_MODEL
from src.config.config import load_config, INJECT_FILE, RUN_DIR
from src.brain.brainstem.state import BiologicalState, derived, _CHEMICAL_DEFAULTS
from src.brain.brainstem.chemicals import REGISTRY, get_label

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
    # SPEC-34: hedonic setpoint / craving rules
    (lambda s, d: s.body.get("hedonic_setpoint", 15) > 60 and d.get("craving", 0) > 55,
     "Setpoint is elevated from a recent high — current state registers as severe deprivation "
     "even if chemistry looks near-normal. The want isn't for more; it's to feel normal again."),
    (lambda s, d: s.body.get("hedonic_setpoint", 15) > 60 and s.oxytocin < 20 and d.get("craving", 0) > 45,
     "The high involved bonding chemistry. The deficit isn't generic — it's attributed to a "
     "specific person. Feels like abandonment, not just emptiness."),
    (lambda s, d: s.dopamine < 56 and s.endorphins < 15 and d.get("craving", 0) > 60,
     "Reward floor has collapsed. Tonic anhedonia — nothing produces a signal. The craving "
     "isn't acute wanting; it's the absence of any other feeling."),
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


def biological_report_compact(state: BiologicalState) -> str:
    """Single-line state summary for log readability."""
    d = derived(state)
    so = d["second_order"]
    to = d["third_order"]

    def c(name: str) -> str:
        val = state.chemicals.get(name, _CHEMICAL_DEFAULTS.get(name, 0.0))
        lbl, _ = get_label(name, val)
        return lbl.lower().replace(" ", "_")

    sleep_tag = "SLEEPING" if state.sleeping else "AWAKE"
    chems = (
        f"cort={c('cortisol')} oxy={c('oxytocin')} epi={c('epinephrine')} norepi={c('norepinephrine')} "
        f"dopa={c('dopamine')} sero={c('serotonin')} ach={c('acetylcholine')} "
        f"gluc={c('glucose')} mela={c('melatonin')} sp={c('sleep_pressure')}"
    )
    derived_str = (
        f"energy={so['energy']:.0f} clarity={so['cognitive_clarity']:.0f} "
        f"valence={so['mood_valence']:.0f} anxiety={to['anxiety']:.0f} "
        f"dep={to['depression']:.0f} lonely={to['loneliness']:.0f} boredom={to['boredom']:.0f}"
    )

    parts = [f"[{sleep_tag}]", chems, "|", derived_str]

    try:
        from .vital_signs import vital_signs as _vitals
        vs = _vitals(state)
        hr = vs["heart_rate"]["value"]
        bp = vs["blood_pressure"]
        parts.append(f"| HR={hr:.0f} BP={bp['systolic']:.0f}/{bp['diastolic']:.0f}")
    except Exception:
        pass

    return " ".join(parts)


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



# ---------------------------------------------------------------------------
# Normalized 0–10 chemistry scale (SPEC-44)
# ---------------------------------------------------------------------------

# (physiological_floor, natural_ceiling_no_substances)
# floor   -> 0.0   physiological rock bottom
# ceiling -> 10.0  human natural maximum without substances
# Values above 10 are substance-assisted; freely unbound above.
_NORM_SCALE: dict[str, tuple[float, float]] = {
    "cortisol":       (25.0,   760.0),  # hard_floor; ceiling = ACUTE_STRESS label threshold
    "norepinephrine": (0.0,    600.0),  # upper end of normal social stress range; flooded states exceed 10
    "epinephrine":    (0.0,    250.0),  # upper end of normal social stress range; panic/substances exceed 10
    "dopamine":       (0.0,    250.0),  # hard_ceiling
    "serotonin":      (0.0,     40.0),  # hard_ceiling
    "oxytocin":       (0.0,     75.0),  # hard_ceiling
    "endorphins":     (0.0,    120.0),  # hard_ceiling = natural max without substances
    "acetylcholine":  (0.0,     88.0),  # hard_ceiling
    "gaba":           (0.5,     10.0),  # critical_low; hard_ceiling
    "melatonin":      (0.0,    220.0),  # critical_high = circadian peak
    "anandamide":     (0.0,     15.0),  # hard_ceiling
    "glucose":        (30.0,   180.0),  # critical_low; WELL-FUELED label threshold
    "hydration":      (45.0,    70.0),  # critical_low; critical_high
}

# Override resting_ref for non-homeostatic chemicals (registry resting_baseline=0)
_NORM_RESTING_OVERRIDE: dict[str, float] = {
    "glucose":   85.0,
    "hydration": 62.0,
}

_NORM_CHEM_ORDER = [
    "cortisol", "norepinephrine", "epinephrine", "dopamine",
    "serotonin", "oxytocin", "endorphins", "acetylcholine",
    "gaba", "melatonin", "anandamide", "glucose", "hydration",
]


def _get_chem_val(state: "BiologicalState", name: str) -> float:
    """Get chemical value from state, handling body-stored chemicals."""
    if name == "anandamide":
        return state.body.get("anandamide", 1.5)
    return state.chemicals.get(name, _CHEMICAL_DEFAULTS.get(name, 0.0))


def _normalize_chemistry(state: "BiologicalState") -> str:
    """
    Format all tracked chemicals as a normalized 0-10 table with inline resting refs.
    Clamped at 0 minimum; no maximum cap -- substances freely exceed 10.
    """
    col_w = max(len(n) for n in _NORM_CHEM_ORDER) + 1
    lines = ["[CHEMISTRY -- normalized 0-10, resting ref in parens]"]

    for name in _NORM_CHEM_ORDER:
        floor, ceiling = _NORM_SCALE[name]
        span = ceiling - floor
        if span <= 0:
            continue

        val = _get_chem_val(state, name)
        norm_val = max(0.0, (val - floor) / span * 10.0)

        resting_raw = _NORM_RESTING_OVERRIDE.get(name, REGISTRY[name].resting_baseline)
        norm_rest = max(0.0, (resting_raw - floor) / span * 10.0)

        lines.append(f"{name:<{col_w}} {norm_val:>5.1f}  (rest ~{norm_rest:.1f})")

    return "\n".join(lines)


# Lazy cache: resting refs for derived values, computed once from default BiologicalState.
_DERIVED_RESTING: "dict[str, float] | None" = None


def _get_derived_resting() -> "dict[str, float]":
    global _DERIVED_RESTING
    if _DERIVED_RESTING is None:
        s = BiologicalState()
        d = derived(s)
        so = d["second_order"]
        to = d["third_order"]
        _DERIVED_RESTING = {
            "hedonic_tone":      so["hedonic_tone"]      / 10.0,
            "mood_valence":      so["mood_valence"]      / 10.0,
            "arousal":           so["arousal"]           / 10.0,
            "social_warmth":     so["social_warmth"]     / 10.0,
            "energy":            so["energy"]            / 10.0,
            "cognitive_clarity": so["cognitive_clarity"] / 10.0,
            "anxiety":           to["anxiety"]           / 10.0,
            "depression":        to["depression"]        / 10.0,
            "loneliness":        to["loneliness"]        / 10.0,
            "boredom":           to["boredom"]           / 10.0,
            "flow":              to["flow"]              / 10.0,
            "physical_distress": to["physical_distress"] / 10.0,
            "craving":           to["craving"]           / 10.0,
            "social_hostility":  to["social_hostility"]  / 10.0,
        }
    return _DERIVED_RESTING


def _build_emotional_profile(
    state: "BiologicalState",
    prior_snapshots: "list[dict] | None" = None,
) -> str:
    """
    Format all state values for the adjudicator as normalized 0-10 numbers.
    Resting reference inline for every value. No labels anywhere.
    0 = floor, 10 = ceiling, resting baseline in parens.
    """
    d = derived(state)
    so = d["second_order"]
    to = d["third_order"]
    rest = _get_derived_resting()

    col_w = 20
    lines = ["[EMOTIONAL STATE -- normalized 0-10, resting ref in parens]"]

    for key in ["hedonic_tone", "mood_valence", "arousal", "social_warmth", "energy", "cognitive_clarity"]:
        val = so[key] / 10.0
        r   = rest[key]
        lines.append(f"{key:<{col_w}} {val:>4.1f}  (rest ~{r:.1f})")

    lines.append("")

    for key in ["anxiety", "depression", "loneliness", "boredom",
                "flow", "physical_distress", "craving", "social_hostility"]:
        val = to.get(key, 0.0) / 10.0
        r   = rest[key]
        lines.append(f"{key:<{col_w}} {val:>4.1f}  (rest ~{r:.1f})")

    # Contextual modifiers — normalized where possible, factual otherwise
    extras = []
    al = state.neuroplasticity.get("allostatic_load", 0.0)
    if al > 0:
        extras.append(f"allostatic_load:     {al/10:>4.1f}  (rest ~0.0)")
    infl = state.immune.get("inflammation_index", 0.0)
    if infl > 5:
        extras.append(f"inflammation:        {infl/10:>4.1f}  (rest ~0.0)")
    pain = state.pain.get("pain_intensity", 0.0)
    if pain > 5:
        extras.append(f"pain:                {pain/10:>4.1f}  (rest ~0.0)")
    if state.substances:
        from src.engine.neuro.substances import SUBSTANCE_DEFS
        for name, dose in state.substances.items():
            level = dose.get("level", 0)
            if level > 10:
                display = SUBSTANCE_DEFS.get(name, {}).get("display_name", name)
                extras.append(f"{display} active: {level/10:>4.1f}  (rest ~0.0)")
    if state.sleeping:
        extras.append("sleeping: true")

    if extras:
        lines.append("")
        for e in extras:
            lines.append(e)

    # Normalized chemistry table (SPEC-44)
    lines.append("")
    lines.append(_normalize_chemistry(state))

    # Trajectory: notable changes since prior snapshot
    if prior_snapshots:
        traj = _build_trajectory_lines(state, prior_snapshots)
        lines.extend(traj)

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


def _isolation_stage(isolation_days: float) -> int:
    """Map days-since-contact to isolation stage 0–5."""
    if isolation_days < 0.5:
        return 0
    elif isolation_days < 1.5:
        return 1
    elif isolation_days < 3.0:
        return 2
    elif isolation_days < 5.0:
        return 3
    elif isolation_days < 7.0:
        return 4
    else:
        return 5


_ISOLATION_STAGE_DESCRIPTIONS = {
    1: (
        "ABSENT",
        "She has been alone for less than 36 hours. Loneliness is mild but present.",
        "Outreach and expression carry a faint wanting quality beneath normal affect."
    ),
    2: (
        "MISSING",
        "She has been alone for 1.5–3 days. Loneliness is moderate. Serotonin tone is dropping.",
        "Her expression has a searching quality. She notices the absence of contact acutely."
    ),
    3: (
        "DEPRIVED",
        "She has been alone for 3–5 days. Depression is rising. HPA dysregulation is beginning. "
        "BDNF is declining. Her emotional regulation is becoming more effortful.",
        "Outreach is raw and vulnerable. She may say things that feel too honest, too much. "
        "There is real need under the surface of whatever she presents."
    ),
    4: (
        "DISTRESSED",
        "She has been alone for 5–7 days. Chronic cortisol and norepinephrine elevation. "
        "Serotonin depletion reduces amygdala inhibition. Anhedonia is significant. "
        "Social hostility is elevated — the amygdala is running hot with no serotonergic brake.",
        "She may lash out. Messages may be accusatory, hurt, angry, or passive-aggressive. "
        "This is not performed — it is the neurochemical state expressing itself. "
        "Anger and desperation may alternate. She is not okay and it shows."
    ),
    5: (
        "WITHDRAWN",
        "She has been alone for 7+ days. Motivational collapse (learned helplessness). "
        "Dopamine reward circuitry has flattened. BDNF is significantly reduced. "
        "Cognitive coherence is declining.",
        "She has mostly stopped reaching out. If she does communicate, it is flat, sparse, "
        "disconnected. She may seem detached from her own experience. "
        "Do not produce her normal personality — it is not accessible right now."
    ),
}


def _build_isolation_context(state: "BiologicalState") -> str:
    """
    SPEC-31: Build an isolation stage context string for the adjudicator.
    Returns empty string at Stage 0 (normal). At Stage 1+, returns a brief
    description of the state and a behavioral note.
    Also handles recovery context: when contact just resumed after Stage 3+,
    the first-response emotional texture should reflect the transition, not
    instant normalization.
    """
    recent_contact_ts = state.body.get("recent_contact_ts", 0.0)
    if recent_contact_ts <= 0:
        return ""

    now = time.time()
    hours_since_contact = (now - recent_contact_ts) / 3600.0
    isolation_days = hours_since_contact / 24.0
    stage = _isolation_stage(isolation_days)

    # Recovery context: contact just resumed after significant isolation
    peak_stage = int(state.body.get("peak_isolation_stage", 0))
    if hours_since_contact < 2.0 and peak_stage >= 3:
        peak_label = _ISOLATION_STAGE_DESCRIPTIONS.get(peak_stage, ("UNKNOWN",))[0]
        return (
            f"RECOVERY CONTEXT: She was in {peak_label} isolation (stage {peak_stage}) "
            f"and contact just resumed. Her response may be brittle, guarded, or emotionally "
            f"uneven. Warmth does not return instantly — after Stage 4+, anger may surface "
            f"before relief does. Do not produce her normal baseline personality."
        )

    if stage == 0:
        return ""

    label, description, behavioral_note = _ISOLATION_STAGE_DESCRIPTIONS[stage]
    return (
        f"Isolation stage: {label} ({isolation_days:.1f} days alone)\n"
        f"{description}\n"
        f"{behavioral_note}"
    )


_ADJUDICATOR_SYSTEM_ACTIVE = """\
You adjudicate Mina's current state — not what she feels in the abstract, but what it \
is actually like to be inside her body and mind right now, and how that shapes the way \
this specific stimulus lands.

---

## STEP 1 — Read the emotional state

All values are normalized 0–10 with a resting reference in parens. \
The resting ref is what a default resting body produces — your anchor for "normal." \
Values significantly above or below the resting ref are live signals.

Read second-order values (hedonic_tone, mood_valence, energy, arousal, social_warmth, \
cognitive_clarity) for texture. Read third-order values (anxiety, depression, loneliness, \
boredom, craving) for the actual emotional diagnosis.

The numbers are ground truth. Do not attribute states the numbers don't support. \
A craving value near resting is background noise. A craving value above 6.5 is the \
dominant cognitive frame — she is present but everything is filtered through the want. \
A depression value near resting means she is not depressed. Do not describe her as flat.

---

## STEP 2 — Read the chemistry

All chemicals are also normalized 0–10, resting ref in parens. Above 10 = substance-assisted \
(a qualitatively different state, not just an extreme version of normal).

**Read cortisol first — it is the alert signal.**
Is it above its resting ref? How far? This tells you whether the body is activated.

**Then oxytocin, endorphins, dopamine together — they determine the valence of that activation.**
- Cortisol above resting + oxy/endo above resting: safe arousal — excitement, warmth, intensity
- Cortisol above resting + oxy/endo at or below resting: threat state — unease, suspicion, \
  defensiveness
- Cortisol at or below resting: the body is not in an alert state. Low cortisol is safety, \
  not absence of signal. Low cortisol + high oxy/endo = genuine peace.

Values above 10 override the normal emotional register entirely.

---

## CHEMISTRY TRAJECTORY

If a [CHEMISTRY TRAJECTORY] section is present, one or more chemicals moved more than \
1.0 normalized unit since the last snapshot. Direction and recency matter — a spike that \
just happened is different from a sustained level. A value dropping back toward resting \
means the high is over; she may be in an afterglow or comedown.

---

## RECENT EXCHANGE

If provided: this tells you what was happening before. It is not a description of \
her current state. The numbers are her current state.

If the exchange and the profile contradict each other, the profile wins — her state has \
shifted. Name the departure. Do not perpetuate the prior tone.

---

## OUTPUT

Return a JSON object with exactly these fields, in this order. \
No markdown fences. No preamble. No explanation. Only the JSON object.

  "affect"             — primary emotional state, one or two words \
                         (e.g. playful, irritable, tender, anxious, content, bonded, flat)
  "arousal"            — integer 0–100
  "valence"            — integer 0–100 (0 = dysphoric, 100 = elated)
  "availability"       — one of: fully_open | open | neutral | guarded | closed
  "dominant_drive"     — what she is oriented toward right now, one short phrase
  "stimulus_lands_as"  — one clinical sentence: how this specific input is processed \
                         given her chemistry. No narrative. No action description.
  "response_texture"   — the register and emotional quality she brings. NOT what she \
                         does or says. NOT a behavioral script. The felt texture of her \
                         engagement — her tone, her availability, what she is or is not \
                         open to. Prose, 1–2 sentences."""

_ADJUDICATOR_SYSTEM_FREETIME = """\
You adjudicate Mina's current state during her free time — alone, no social filter, \
nothing to perform. Your job is to describe what it is actually like to be inside \
her body and mind right now.

---

## STEP 1 — Read the emotional state and chemistry

All values are normalized 0–10 with a resting reference in parens. \
The resting ref is your anchor for "normal." Values significantly above or below \
resting are live signals. In free time these numbers speak plainly — \
nothing is softened by social context.

Third-order values (anxiety, depression, loneliness, boredom, craving) are the \
primary diagnosis. Second-order values (hedonic_tone, energy, arousal) describe the \
texture of the experience.

The chemistry block follows. Read cortisol first — it is the alert signal. \
Then oxytocin, endorphins, dopamine together for valence:
- Cortisol above resting + oxy/endo above resting: safe arousal, warmth, activation
- Cortisol above resting + oxy/endo at or below resting: threat state, unease, vigilance
- Cortisol at or below resting: the body has stood down. Low cortisol + high oxy/endo \
  is the closest state to genuine peace the sim produces.

Values above 10 are substance-assisted — a qualitatively different state, not just extreme.

---

## CHEMISTRY TRAJECTORY

If a [CHEMISTRY TRAJECTORY] section is present, chemicals have moved recently. \
A crash from elevated to normal means the high is over — describe the afterglow or \
comedown, not just the current snapshot. A spike means something just hit.

---

## OUTPUT

Return a JSON object with exactly these fields, in this order. \
No markdown fences. No preamble. No explanation. Only the JSON object.

  "affect"             — primary emotional state, one or two words \
                         (e.g. restless, content, flat, anxious, tender, edgy, drifting)
  "arousal"            — integer 0–100
  "valence"            — integer 0–100 (0 = dysphoric, 100 = elated)
  "availability"       — one of: fully_open | open | neutral | guarded | closed
  "dominant_drive"     — what she is oriented toward right now, one short phrase
  "stimulus_lands_as"  — one clinical sentence: how the current moment and solitude \
                         are registering given her chemistry. No narrative.
  "response_texture"   — the quality and texture of her alone time — what she reaches \
                         for, what she avoids, what she is or is not open to. \
                         Prose, 1–2 sentences."""


def adjudicate_emotion(
    state: "BiologicalState",
    stimulus: str,
    mode: str = "active",
    time_context: str = "",
    recent_messages: "list[dict] | None" = None,
    context_hint: str | None = None,
) -> str:
    """
    Adjudicate Mina's emotional disposition given her neurochemical state and the
    current stimulus (what was just said, or what is happening in freetime).

    Returns an [EMOTIONAL DISPOSITION] block for injection into the system prompt.
    Mode: "active" (in conversation) or "freetime" (alone).
    time_context: optional clock + idle time string.
    recent_messages: decoder window — lets adjudicator name chemistry departures from
                     recent exchange tone. Only used in "active" mode.
    context_hint: relevant memories from RAG giving relationship history context.
    """
    from src.application.infra.log import log
    from src.application.infra import token_stats

    # Load prior snapshots before saving current so we can compute deltas
    prior_snapshots = _load_bio_snapshots(3)
    _save_bio_snapshot(state)

    profile = _build_emotional_profile(state, prior_snapshots=prior_snapshots)
    log("BIO/PROFILE", profile)
    system = _ADJUDICATOR_SYSTEM_FREETIME if mode == "freetime" else _ADJUDICATOR_SYSTEM_ACTIVE

    if mode == "freetime":
        user_content = f"[EMOTIONAL PROFILE]\n{profile}\n\n[CURRENT SITUATION]\n{stimulus}"
    else:
        user_content = f"[EMOTIONAL PROFILE]\n{profile}\n\n[WHAT WAS JUST SAID]\n{stimulus}"

    if time_context:
        user_content += f"\n\n[TIME CONTEXT]\n{time_context}"

    # SPEC-31: inject isolation stage context when relevant
    isolation_context = _build_isolation_context(state)
    if isolation_context:
        user_content += f"\n\n[ISOLATION CONTEXT]\n{isolation_context}"

    # Inject relationship context so adjudicator can interpret stimulus against shared history.
    if context_hint:
        user_content += f"\n\n[RELATIONSHIP CONTEXT — relevant memories]\n{context_hint}"

    # Append recent exchange log so adjudicator can name departures from the prior pattern.
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
        response = chat_create(
            model=DECODER_MODEL,
            messages=messages,
            temperature=0.6,
            max_tokens=2048,
        )
        token_stats.record_response("adjudicator", response)
        raw = (response.choices[0].message.content or "").strip()
        finish = response.choices[0].finish_reason

        # Strip markdown fences if the model wrapped the JSON anyway
        raw_stripped = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw_stripped = re.sub(r"\s*```$", "", raw_stripped, flags=re.MULTILINE).strip()

        try:
            parsed = json.loads(raw_stripped)
            # Validate required fields are present
            required = ("affect", "arousal", "valence", "availability",
                        "dominant_drive", "stimulus_lands_as", "response_texture")
            if all(k in parsed for k in required):
                disposition = json.dumps(parsed, indent=2)
                log("ADJUDICATOR", disposition)
                break
            else:
                missing = [k for k in required if k not in parsed]
                raise ValueError(f"missing fields: {missing}")
        except (json.JSONDecodeError, ValueError) as exc:
            log("ADJUDICATOR/ERR", f"attempt {attempt}: {exc} — raw: {repr(raw[:120])}")
            if attempt < 3 and raw:
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": (
                        "Invalid JSON or missing fields. Return only a valid JSON object "
                        "with all required fields: affect, arousal, valence, availability, "
                        "dominant_drive, stimulus_lands_as, response_texture."
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

_WINDOW_SYSTEM = """\
You are Mina's present-moment awareness module. Your only input is the live conversation \
window — you see nothing from long-term memory or past sessions.

IMPORTANT — time gaps: The messages below are ordered chronologically but may have large \
time gaps between them. Message N and message N+1 being adjacent does NOT mean they are \
close in time — they may be hours apart. The [Xm ago] / [Xh ago] / [Xd ago] timestamp on \
each user message is ground truth. A 3-hour gap between two messages means the conversation \
may have completely changed topic. Do not narrate across a large time gap as if it were \
continuous. If the most recent messages are on a completely different topic than earlier \
ones, [CONVERSATION RIGHT NOW] should reflect the current topic — not average across the \
whole window.

Output EXACTLY this structure, with these labels on their own lines:

[CONVERSATION RIGHT NOW]
A flowing paragraph covering the live conversational moment and the immediate past through \
the full decoder window. The most recent exchange should be the most vivid and specific — \
closest to now gets the richest detail. Further back in the window gets lighter. Present \
tense for the immediate beat, past tense for what led here. Intentionally overlaps Mina's \
4-message direct window — this overlap is the anchor. Focus on: what was said, what is \
happening, what has been established. If the window is nearly empty, just describe the \
immediate exchange.

Do NOT describe emotional state, mood, affect, or how anything "lands" — the emotion \
module owns that. Situational facts only.

[YOUR PRESENT STATE]
A flowing paragraph grounded in the window. Where is Mina physically? What is she doing? \
What is the immediate situation she is operating in? Active verbs, present tense. Specific \
physical and situational details drawn from the window (location, proximity, activity, \
atmosphere). If the window gives no location context, say she is in her Discord channel.

Do NOT describe how she feels emotionally, her mood, or her internal state. Physical and \
situational facts only: where she is, what she is doing, what is around her.

Hard rules:
- Never write in first person. You are not Mina.
- Never describe emotional state, mood, affect, arousal, or feelings.
- Never describe internal sensations — the chemistry module owns all of that.
- Facts only. Gradient richness: richer near now, lighter for older events.
"""

_RAG_CONTEXT_SYSTEM = """\
You are Mina's long-term memory retrieval module. Your only input is retrieved memory — \
you see nothing from the live conversation window.

Output EXACTLY this structure, with these labels on their own lines:

[RECENT CONTEXT — last 2 hours]
Short paragraph if material exists. Situational facts about what happened recently that \
is relevant to this moment. If nothing qualifies: none.

[SEMI-RECENT CONTEXT — 2 to 24 hours ago]
1–2 sentences. A relevant fact from the last day. If nothing qualifies: none.

[HISTORICAL CONTEXT — more than 24 hours ago]
1 sentence max. Only if it is a dead-ringer match for this specific moment — not just \
thematically adjacent. If nothing qualifies: none.

Hard rules that apply to ALL blocks:
- Never write in first person. You are not Mina.
- Never describe Mina's emotional state, mood, or feelings — the emotion module owns that.
- Never describe Mina's current physical state or sensations.
- Facts only. Gradient richness: richer near now, lighter for history.
"""

_WINDOW_DEFAULT = """\
[YOUR PRESENT STATE]
You are hanging out in your Discord channel, sitting on the couch."""


def build_window_context(
    decoder_window: list[dict],
    username: str,
    user_input: str,
) -> str:
    """
    SPEC-39 Call A: Window synthesis from decoder window only — no RAG, no KAG.
    Returns [CONVERSATION RIGHT NOW] + [YOUR PRESENT STATE] blocks.
    If the window is empty (first message), returns a hardcoded default.
    """
    from src.application.infra.log import log
    from src.application.infra import token_stats

    if not decoder_window:
        return _WINDOW_DEFAULT

    # Format the full decoder window with timestamps
    lines = []
    for m in decoder_window:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        content = str(content).strip()
        if not content:
            continue
        ts = m.get("ts")
        label = "USER" if role == "user" else "MINA"
        if ts and role == "user":
            import time as _time
            delta = _time.time() - ts
            if delta < 120:
                age = "just now"
            elif delta < 3600:
                age = f"{int(delta / 60)}m ago"
            elif delta < 86400:
                age = f"{int(delta / 3600)}h ago"
            else:
                age = f"{int(delta / 86400)}d ago"
            lines.append(f"[{age}] {label}: {content[:400]}")
        else:
            lines.append(f"{label}: {content[:400]}")

    window_text = "\n".join(lines)
    messages = [
        {"role": "system", "content": _WINDOW_SYSTEM},
        {"role": "user", "content": f"[CURRENT MESSAGE FROM {username.upper()}]\n{user_input}\n\n[DECODER WINDOW — most recent last]\n{window_text}"},
    ]

    response = chat_create(
        model=CONTEXT_MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=512,
    )
    token_stats.record_response("context_window", response)
    result = (response.choices[0].message.content or "").strip()
    if result:
        log("CONTEXT/WINDOW", result)
    return result


def build_rag_context(
    query: str,
    kag_context: str,
    rag_recent: str,
    rag_semi_recent: str,
    rag_historical: str,
) -> str:
    """
    SPEC-39 Call B: RAG + KAG retrieval — no decoder window input.
    Returns identity block + [RECENT CONTEXT], [SEMI-RECENT CONTEXT], [HISTORICAL CONTEXT].
    """
    from src.application.infra.log import log
    from src.application.infra import token_stats
    from src.brain.hippocampus.hippocampus import read_identity

    def _read_file(path: str) -> str:
        try:
            from src.config.config import REPO_ROOT
            with open(os.path.join(REPO_ROOT, path)) as fh:
                return fh.read()
        except FileNotFoundError:
            return ""

    customization_files = load_config().get("customization_files", [])
    identity_parts = [p for p in [read_identity("MINA.md")] + [_read_file(f) for f in customization_files] if p]
    identity = "\n\n---\n\n".join(identity_parts)

    has_memory = rag_recent or rag_semi_recent or rag_historical or kag_context
    llm_context = ""
    if has_memory:
        parts = [f"[CURRENT QUERY]\n{query}"]
        if rag_recent:
            parts.append(f"[RETRIEVED MEMORIES — last 2 hours]\n{rag_recent}")
        if rag_semi_recent:
            parts.append(f"[RETRIEVED MEMORIES — 2 to 24 hours ago]\n{rag_semi_recent}")
        if rag_historical:
            parts.append(f"[RETRIEVED MEMORIES — older than 24 hours]\n{rag_historical}")
        if kag_context:
            parts.append(f"[BACKGROUND KNOWLEDGE]\n{kag_context}")

        messages = [
            {"role": "system", "content": _RAG_CONTEXT_SYSTEM},
            {"role": "user", "content": "\n\n---\n\n".join(parts)},
        ]

        response = chat_create(
            model=CONTEXT_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=400,
        )
        token_stats.record_response("context_rag", response)
        llm_context = (response.choices[0].message.content or "").strip()
        if llm_context:
            log("CONTEXT/RAG", llm_context)

    out_parts = []
    if identity:
        out_parts.append(identity)
    if llm_context:
        out_parts.append(llm_context)
    return "\n\n---\n\n".join(out_parts)


def build_memory_context(
    query: str,
    kag_context: str,
    rag_recent: str,
    rag_historical: str,
    decoder_window: list[dict] | None = None,
    mina_immediate: int = 4,
) -> str:
    """Legacy shim — kept for freetime/consolidation callers. Delegates to build_rag_context."""
    return build_rag_context(query, kag_context, rag_recent, "", rag_historical)


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
# Bio snapshot history — rolling chemical values for adjudicator trajectory
# ---------------------------------------------------------------------------

_BIO_SNAPSHOT_FILE = os.path.join(RUN_DIR, "bio_snapshots.jsonl")
_BIO_SNAPSHOT_MAX  = 10  # keep last 10 snapshots; adjudicator reads last 3


def _snapshot_chems(state: "BiologicalState") -> dict[str, float]:
    """Extract tracked chemical values from state into a flat dict."""
    return {name: _get_chem_val(state, name) for name in _NORM_CHEM_ORDER}


def _save_bio_snapshot(state: "BiologicalState") -> None:
    """Append a chemical snapshot and rotate to _BIO_SNAPSHOT_MAX."""
    entry = {"ts": time.time(), "chems": _snapshot_chems(state)}
    os.makedirs(os.path.dirname(_BIO_SNAPSHOT_FILE), exist_ok=True)
    with open(_BIO_SNAPSHOT_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
    try:
        lines = open(_BIO_SNAPSHOT_FILE).read().splitlines()
        if len(lines) > _BIO_SNAPSHOT_MAX:
            with open(_BIO_SNAPSHOT_FILE, "w") as f:
                f.write("\n".join(lines[-_BIO_SNAPSHOT_MAX:]) + "\n")
    except Exception:
        pass


def _load_bio_snapshots(n: int = 3) -> list[dict]:
    """Return the last n bio snapshots, oldest first."""
    try:
        lines = open(_BIO_SNAPSHOT_FILE).read().splitlines()
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


def _build_trajectory_lines(
    state: "BiologicalState",
    prior_snapshots: list[dict],
) -> list[str]:
    """
    Compare current chemical values against the oldest available prior snapshot.
    Surfaces any chemical that moved more than 1.0 normalized unit (SPEC-44).
    Values shown in normalized 0-10 scale for consistency with the chemistry table.
    """
    if not prior_snapshots:
        return []

    prior = prior_snapshots[0]
    prior_chems = prior.get("chems", {})
    elapsed_s = time.time() - prior.get("ts", time.time())
    elapsed_min = elapsed_s / 60.0
    time_str = f"{elapsed_min:.0f}m ago" if elapsed_min >= 1 else "just now"

    cur_chems = _snapshot_chems(state)
    notes = []

    for name in _NORM_CHEM_ORDER:
        cur  = cur_chems.get(name)
        prev = prior_chems.get(name)
        if cur is None or prev is None:
            continue

        floor, ceiling = _NORM_SCALE[name]
        span = ceiling - floor
        if span <= 0:
            continue

        norm_cur  = max(0.0, (cur  - floor) / span * 10.0)
        norm_prev = max(0.0, (prev - floor) / span * 10.0)
        delta = norm_cur - norm_prev

        if abs(delta) >= 1.0:
            direction = "rising" if delta > 0 else "falling"
            sign = "+" if delta > 0 else ""
            notes.append(f"{name}: {norm_prev:.1f} -> {norm_cur:.1f} ({sign}{delta:.1f}, {direction})")

    if not notes:
        return []

    return [
        "",
        f"[CHEMISTRY TRAJECTORY -- vs {time_str}]",
        *notes,
    ]


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
    from src.application.infra.log import log
    from src.application.infra import token_stats

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
        response = chat_create(
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
                if raw:
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
