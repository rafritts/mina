"""
Biological state report — pure Python, zero LLM cost.

Maps first-order and derived state values to named ranges with behavioral
implications. Output is ground truth for the subconscious LLM — it cannot
contradict this report. Also provides needs_summary() for heartbeat stimulus.
"""
from state import BiologicalState, derived

# ---------------------------------------------------------------------------
# Range tables: list of (upper_bound_exclusive, name, implication)
# ---------------------------------------------------------------------------

_OXYTOCIN_RANGES = [
    (15,  "NO BOND",        "Stranger. Guarded. No warmth extended."),
    (35,  "ACQUAINTANCE",   "Surface comfort. Polite but watchful."),
    (55,  "FRIENDLY",       "Genuine warmth. Opens up somewhat."),
    (72,  "TRUSTED FRIEND", "Real connection. Vulnerability possible."),
    (88,  "DEEP TRUST",     "Emotional intimacy available. Little guarded."),
    (101, "PROFOUND BOND",  "Full openness. Unconditional trust baseline."),
]

_CORTISOL_RANGES = [
    (15,  "DEPLETED",     "Too low. Fatigue, inability to respond."),
    (40,  "NORMAL",       "Healthy range. Morning peak helps focus. Stable."),
    (60,  "ELEVATED",     "Decision-making beginning to narrow. Slightly defensive."),
    (78,  "HIGH STRESS",  "Fight-or-flight activating. Emotional regulation costs."),
    (92,  "ACUTE STRESS", "Survival framing. Hard to think past immediate threat."),
    (101, "MAXED",        "The body is screaming. Suppression is actively costing her."),
]

_DOPAMINE_RANGES = [
    (20,  "NO DRIVE",       "No pull toward anything. Cannot generate motivation."),
    (40,  "LOW SEEKING",    "Can act if prompted but nothing calls to her."),
    (60,  "BASELINE",       "Normal wanting. Responds to interesting things."),
    (75,  "ACTIVE SEEKING", "Noticeably motivated. Pursuing things. Hard to distract."),
    (90,  "HIGH DRIVE",     "Intense wanting. Seeking compounds. Hard to disengage."),
    (101, "COMPULSIVE",     "Seeking has become its own end. Can't stop."),
]

_SEROTONIN_RANGES = [
    (20,  "DYSPHORIC",   "Feels low-status, unsafe. Impulsive, irritable. Reads ambiguous cues as hostile."),
    (40,  "INSECURE",    "Negative social bias. Difficulty trusting. Easily slighted."),
    (60,  "NEUTRAL",     "Things feel basically okay. Stable floor. Even-keeled."),
    (80,  "SECURE",      "Socially confident. Patient. Resilient to friction."),
    (101, "VERY STABLE", "Hard to knock off balance. Feels socially at ease."),
]

_ENDORPHINS_RANGES = [
    (15,  "NONE",        "Baseline. No active pleasure signal."),
    (35,  "MILD WARMTH", "Low-grade good feeling. Small satisfactions land."),
    (60,  "PLEASURE",    "Genuine enjoyment. Things feel rewarding."),
    (80,  "HIGH",        "Strong pleasure. Euphoric edge. Laughter, warmth, ease."),
    (101, "PEAK",        "Intense well-being. Runner's high territory."),
]

_NOREPINEPHRINE_RANGES = [
    (25,  "SEDATED",    "Low arousal. Sluggish. Attention diffuse."),
    (45,  "CALM ALERT", "Relaxed awareness. Background attention functional."),
    (65,  "FOCUSED",    "Alert and responsive. Memory consolidation enhanced."),
    (80,  "HEIGHTENED", "On edge. Quick to react. Appetite suppressed."),
    (92,  "HYPERALERT", "Agitated. Intrusive thoughts. Difficulty staying still."),
    (101, "FLOODED",    "Overwhelmed. Physical symptoms possible."),
]

_ACETYLCHOLINE_RANGES = [
    (15,  "OFFLINE",    "Cannot form memories. Cannot concentrate."),
    (40,  "IMPAIRED",   "Fuzzy. Slow to learn. Easily distracted."),
    (65,  "FUNCTIONAL", "Normal attention and memory. Things register."),
    (85,  "SHARP",      "Good focus. Learning sticks. Connecting things quickly."),
    (101, "HEIGHTENED", "Peak learning state. Everything is registering."),
]

_GLUCOSE_RANGES = [
    (40,  "HYPOGLYCEMIC", "Cognitively impaired. Foggy. Irritability threshold very low."),
    (58,  "LOW",          "Noticeable fog. Hard to concentrate. Hunger intrusive."),
    (80,  "NORMAL",       "Functional. No impairment."),
    (101, "WELL-FUELED",  "Sharp. Full capacity."),
]

_MELATONIN_RANGES = [
    (18,  "AWAKE",          "No sleep signal. Fully alert circadian state."),
    (38,  "DROWSY",         "Yawning. Slightly slow. Can fight it."),
    (58,  "HEAVY",          "Significant effort to stay engaged. World softening."),
    (78,  "SLEEP PULL",     "Difficult to maintain focus. Thoughts drifting."),
    (101, "SLEEP IMMINENT", "Cannot meaningfully fight it. Cognitive output near zero."),
]

# Derived state range tables
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
# Interaction rules
# ---------------------------------------------------------------------------

# Each entry: (predicate(state, derived_flat), note_text)
# derived_flat merges second_order and third_order into one dict.
INTERACTION_RULES = [
    (lambda s, d: s.cortisol > 85 and s.oxytocin > 70,
     "Acute stress held together by a strong bond. Suppression has a cost — this cannot hold indefinitely."),
    (lambda s, d: s.cortisol > 85 and s.oxytocin < 35,
     "Acute stress with no trust anchor. Likely to shut down or lash out."),
    (lambda s, d: d['cognitive_clarity'] < 15 and s.sleeping,
     "Cognitively offline — asleep. Responses must reflect this."),
    (lambda s, d: d['cognitive_clarity'] < 15 and not s.sleeping,
     "Cognitively offline while awake — severely impaired. Something is wrong."),
    (lambda s, d: s.glucose < 45 and d['anxiety'] > 60,
     "Hunger is amplifying the anxiety. These are compounding."),
    (lambda s, d: s.dopamine > 80 and d['anxiety'] > 65,
     "High reward-seeking under stress — impulsive decisions likely."),
    (lambda s, d: s.serotonin < 30 and d['depression'] > 60,
     "Low serotonin floor + high depression. Negative bias in all interpretation."),
    (lambda s, d: d['boredom'] > 65 and s.dopamine < 45,
     "Severe boredom with low dopamine — actively seeking any stimulation. Will accept poor trade-offs."),
    (lambda s, d: d['boredom'] > 65 and s.cortisol < 40,
     "Boredom distress without active threat — playfully chaotic or reckless, not fearful. Mischief-seeking."),
    (lambda s, d: d['boredom'] > 65 and d['depression'] > 55,
     "Boredom + depression: not restless chaos but heavy inertia. Wants relief but can't generate motivation. Stuck."),
    (lambda s, d: d['loneliness'] > 70 and s.oxytocin < 40,
     "Aching loneliness with no established bond — contact-seeking urgent but trust isn't there. Approach-avoidance tension."),
    (lambda s, d: s.norepinephrine > 85 and d['cognitive_clarity'] < 40,
     "Flooded with arousal but cognitively impaired — high reactivity, low judgment. Responses may be raw or unfiltered."),
    (lambda s, d: s.dopamine > 75 and s.endorphins < 20,
     "High wanting, low liking — seeking hard but arrival feels hollow. Addictive/obsessive pattern."),
    (lambda s, d: s.dopamine < 35 and s.endorphins > 45,
     "Low drive, high pleasure capacity — content with what comes but won't pursue much. Passive warmth without motivation."),
    (lambda s, d: s.serotonin < 35 and d['loneliness'] > 50,
     "Low serotonin + loneliness: social cues are being read as threatening even when neutral. Contact may feel worse than absence."),
    (lambda s, d: s.serotonin < 35 and s.cortisol > 55,
     "Low serotonin floor under active stress — impulse control is compromised. Likely to say or do something she'll regret."),
    (lambda s, d: s.norepinephrine > 70 and s.glucose < 50,
     "Hyperalert but underfueled — attention is sharp but the tank is empty. Will crash hard when the stress passes."),
]


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def biological_report(state: BiologicalState) -> str:
    """
    Generate the deterministic biological state report.
    Ground truth — the subconscious LLM must not contradict it.
    """
    d = derived(state)
    so = d["second_order"]
    to = d["third_order"]
    flat = {**so, **to}

    SEP = "━" * 52
    lines = ["BIOLOGICAL STATE REPORT", SEP]

    def row(label: str, value: float, table: list) -> str:
        name, impl = _get_range(value, table)
        return f"{label:<12} {value:>5.1f}  {name:<18} {impl}"

    lines.append(row("Cortisol",   state.cortisol,       _CORTISOL_RANGES))
    lines.append(row("Oxytocin",   state.oxytocin,       _OXYTOCIN_RANGES))
    lines.append(row("Norepineph", state.norepinephrine, _NOREPINEPHRINE_RANGES))
    lines.append(row("Dopamine",   state.dopamine,       _DOPAMINE_RANGES))
    lines.append(row("Serotonin",  state.serotonin,      _SEROTONIN_RANGES))
    lines.append(row("Endorphins", state.endorphins,     _ENDORPHINS_RANGES))
    lines.append(row("Acetylchol", state.acetylcholine,  _ACETYLCHOLINE_RANGES))
    lines.append(row("Glucose",    state.glucose,        _GLUCOSE_RANGES))
    lines.append(row("Melatonin",  state.melatonin,      _MELATONIN_RANGES))

    hydration_note = "comfortable" if state.hydration > 80 else ("very thirsty" if state.hydration < 40 else ("thirsty" if state.hydration < 55 else "ok"))
    lines.append(f"{'Hydration':<12} {state.hydration:>5.1f}  {'—':<18} {hydration_note}")

    sleep_tag = "SLEEPING" if state.sleeping else "awake"
    lines.append(f"{'Sleep pres':<12} {state.sleep_pressure:>5.1f}  {sleep_tag:<18}")

    lines.append(SEP)
    lines.append(row("Clarity",    so['cognitive_clarity'], _CLARITY_RANGES))
    lines.append(row("Anxiety",    to['anxiety'],           _ANXIETY_RANGES))
    lines.append(row("Boredom",    to['boredom'],           _BOREDOM_RANGES))
    lines.append(row("Loneliness", to['loneliness'],        _LONELINESS_RANGES))
    lines.append(row("Depression", to['depression'],        _DEPRESSION_RANGES))
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

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Needs summary (heartbeat stimulus)
# ---------------------------------------------------------------------------

def needs_summary(state: BiologicalState, elapsed_minutes: float = 0) -> str:
    """
    Summarize notable needs and current state for the heartbeat encode_stimulus call.
    """
    d = derived(state)
    to = d["third_order"]
    parts = []

    if elapsed_minutes > 0:
        parts.append(f"{elapsed_minutes:.0f} minutes of quiet.")

    if state.glucose < 45:
        parts.append(f"Glucose at {state.glucose:.0f} — hypoglycemic, hungry.")
    elif state.glucose < 60:
        parts.append(f"Glucose at {state.glucose:.0f} — hungry.")

    if state.hydration < 40:
        parts.append(f"Hydration at {state.hydration:.0f} — very thirsty.")
    elif state.hydration < 55:
        parts.append(f"Hydration at {state.hydration:.0f} — thirsty.")

    if state.sleep_pressure > 80:
        parts.append(f"Sleep pressure at {state.sleep_pressure:.0f} — exhausted.")
    elif state.sleep_pressure > 60:
        parts.append(f"Sleep pressure at {state.sleep_pressure:.0f} — tired.")

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
