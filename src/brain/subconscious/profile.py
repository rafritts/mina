"""
Emotional profile builder — normalized 0-10 state table for the Emotion Pillar.
Includes normalization constants, trajectory computation, and isolation context.
"""
import time

from src.brain.brainstem.state import BiologicalState, derived, _CHEMICAL_DEFAULTS
from src.engine.chem.registry import REGISTRY
from src.brain.subconscious.snapshot_history import (
    save_bio_snapshot, load_bio_snapshots, _snapshot_chems, _SNAPSHOT_CHEMS,
)
from src.brain.subconscious.somatic import build_somatic_narrative

# ---------------------------------------------------------------------------
# Normalization constants
# ---------------------------------------------------------------------------

# (physiological_floor, natural_ceiling_no_substances)
# Values above 10 are substance-assisted; freely unbound above.
_NORM_SCALE: dict[str, tuple[float, float]] = {
    "cortisol":       (25.0,   760.0),
    "norepinephrine": (0.0,    600.0),
    "epinephrine":    (0.0,    250.0),
    "dopamine":       (0.0,    250.0),
    "serotonin":      (0.0,     40.0),
    "oxytocin":       (0.0,     75.0),
    "endorphins":     (0.0,    120.0),
    "acetylcholine":  (0.0,     88.0),
    "gaba":           (0.5,     10.0),
    "melatonin":      (0.0,    220.0),
    "anandamide":     (0.0,     15.0),
    "glucose":        (30.0,   180.0),
    "hydration":      (45.0,    70.0),
}

_NORM_RESTING_OVERRIDE: dict[str, float] = {
    "glucose":   85.0,
    "hydration": 62.0,
}

_NORM_CHEM_ORDER = _SNAPSHOT_CHEMS


def _get_chem_val(state: BiologicalState, name: str) -> float:
    if name == "anandamide":
        return state.body.get("anandamide", 1.5)
    return state.chemicals.get(name, _CHEMICAL_DEFAULTS.get(name, 0.0))


def _normalize_chemistry(state: BiologicalState) -> str:
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


# ---------------------------------------------------------------------------
# Resting reference cache
# ---------------------------------------------------------------------------

_DERIVED_RESTING: "dict[str, float] | None" = None


def _get_derived_resting() -> dict[str, float]:
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


# ---------------------------------------------------------------------------
# Trajectory
# ---------------------------------------------------------------------------

def _build_trajectory_lines(
    state: BiologicalState,
    prior_snapshots: list[dict],
) -> list[str]:
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
# Isolation context (SPEC-31)
# ---------------------------------------------------------------------------

def _build_isolation_context(state: BiologicalState) -> str:
    recent_contact_ts = state.body.get("recent_contact_ts", 0.0)
    if recent_contact_ts <= 0:
        return ""

    now = time.time()
    hours_since_contact = (now - recent_contact_ts) / 3600.0
    if hours_since_contact < 12.0:
        return ""

    isolation_days = hours_since_contact / 24.0

    peak_stage = int(state.body.get("peak_isolation_stage", 0))
    if hours_since_contact < 2.0 and peak_stage >= 3:
        return f"Contact just resumed after {peak_stage * 2:.0f}+ days of isolation."

    return f"Time since last human contact: {isolation_days:.1f} days"


# ---------------------------------------------------------------------------
# Emotional profile
# ---------------------------------------------------------------------------

def _build_emotional_profile(
    state: BiologicalState,
    prior_snapshots: "list[dict] | None" = None,
) -> str:
    """
    Format all state values for the Emotion Pillar as normalized 0-10 numbers.
    Includes chemistry table, trajectory, and LLM-generated somatic narrative.
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

    lines.append("")
    lines.append(_normalize_chemistry(state))

    if prior_snapshots:
        traj = _build_trajectory_lines(state, prior_snapshots)
        lines.extend(traj)

    if not state.sleeping:
        somatic = build_somatic_narrative("\n".join(lines))
        if somatic:
            lines.append("")
            lines.append("[SOMATIC STATE]")
            lines.append(somatic)

    return "\n".join(lines)
