"""
Chemistry function — deterministic mapping from encoder output to Class 1 deltas.

Encoder output → axis activations (0-10 integers) → weighted sum per chemical
→ EVENT_GAIN scale → source-side negative feedback → PFC frontend regulation
→ receptor sensitivity → apply delta.

Only touches Class 1 chemicals (DA, 5-HT, NE, epinephrine). Class 2/3/4 are
tick-only and never receive direct encoder deltas. The absence of axis_weights
in a chemical's params entry is the documentation of this.

Salience floor: axis values ≤ 2 are treated as zero (noise suppression).
"""
from __future__ import annotations

from .state import ChemicalState
from .params import (
    CHEMICAL_PARAMS,
    PFC_REGULATION_BASE,
    BIG5_GAIN_BIAS,
    BIG5_AXIS_BIAS,
    EVENT_GAIN,
    CHEMICAL_TOTAL_CAP_MULT,
)

_SALIENCE_FLOOR = 2  # axis values ≤ this are ignored

# Register-shift impulse in normalized units, added after EVENT_GAIN.
# A full stake (magnitude 10, axis 10, probability 1) is sized so PFC and
# feedback still leave epinephrine around gap +4 to +5 — a felt rush, not a
# tenth of a nanomole. Cold opens stay small because probability stays low.
_REGISTER_IMPULSE = {
    "epinephrine": 8.0,
    "norepinephrine": 5.5,
}
_STAKE_AXES = ("threat", "social_threat", "loss", "arousal", "romance", "bonding")


def stake_probability(relationship_modifier: float, turn_depth: int) -> float:
    """
    How likely this event is to matter.

    The relationship file is one prior (empty file → stranger, 0.1). A live
    exchange is the other: a dozen turns in, a breakup is not a cold open
    even when memory/relationships/ has not been written yet.
    """
    try:
        prior = float(relationship_modifier)
    except (TypeError, ValueError):
        prior = 0.1
    prior = max(0.1, min(1.0, prior))
    exchanges = max(0, int(turn_depth) - 1)
    density = min(1.0, exchanges / 12.0)
    live = 0.1 + 0.75 * density
    return round(max(prior, live), 3)


def _axis(encoder_output: dict, name: str) -> float:
    try:
        return max(0.0, min(10.0, float(encoder_output.get(name, 0) or 0)))
    except (TypeError, ValueError):
        return 0.0


def _register_impulse(
    chemical: str,
    encoder_output: dict,
    relationship_modifier: float,
    turn_depth: int,
) -> float:
    """Normalized-unit adrenaline/alertness burst for a real register shift."""
    full = _REGISTER_IMPULSE.get(chemical)
    if not full:
        return 0.0
    if not encoder_output.get("register_shift"):
        return 0.0
    if not encoder_output.get("directed_at_mina", False):
        return 0.0
    magnitude = _axis(encoder_output, "expected_magnitude") / 10.0
    if magnitude < 0.3:
        return 0.0
    stake = max(_axis(encoder_output, axis) for axis in _STAKE_AXES) / 10.0
    if stake < 0.4:
        return 0.0
    probability = stake_probability(relationship_modifier, turn_depth)
    return full * magnitude * stake * probability


def _get_normalized(state: ChemicalState, chemical: str) -> float:
    """Current 0-10 normalized value for a chemical."""
    lvl = state.levels.get(chemical)
    p   = CHEMICAL_PARAMS.get(chemical)
    if not lvl or not p:
        return 0.0
    combined = lvl.tonic + lvl.phasic
    return combined / p["normalization_max"] * 10.0


def apply_chemistry(
    encoder_output: dict,
    state: ChemicalState,
    big5: dict[str, float],
    relationship_modifier: float = 1.0,
    turn_depth: int = 0,
) -> dict[str, float]:
    """
    Apply encoder axis activations as Class 1 phasic deltas.
    Mutates state.levels[chemical].phasic in place.

    Returns {chemical: delta_nM} for non-trivial Class 1 applications
    (for mind-stream / diagnostics). Empty when the turn is under the
    salience floor or all deltas round to ~0.

    encoder_output: {
      "salience": 0-10, "threat": 0-10, ...,
      "directed_at_mina": bool,
      "register_shift": bool, "expected_magnitude": 0-10,
      "channel": "dialogue" | "action"
    }
    big5: {"neuroticism": 65, "extraversion": 48, ...}
    relationship_modifier: multiplier from relationship state (bonding dimension)
    turn_depth: messages in the live window, including this one. Raises stake
    probability so an in-progress conversation is not treated as a stranger.
    """
    applied: dict[str, float] = {}

    # Build effective axis weights per chemical from Big 5 biases
    effective_weights = _build_effective_weights(big5)

    for chem, p in CHEMICAL_PARAMS.items():
        if p["class"] != 1:
            continue
        weights = effective_weights.get(chem, p.get("axis_weights", {}))
        if not weights:
            continue

        # Weighted sum of axis activations
        raw_delta = 0.0
        for axis, weight in weights.items():
            axis_val = encoder_output.get(axis, 0)
            if axis_val <= _SALIENCE_FLOOR and weight > 0:
                axis_val = 0  # floor for positive-weight axes
            raw_delta += axis_val * weight

        impulse = _register_impulse(
            chem, encoder_output, relationship_modifier, turn_depth
        )
        if abs(raw_delta) < 0.01 and impulse <= 0:
            continue

        # Scale by salience and relationship modifier
        salience_scale = encoder_output.get("salience", 5) / 5.0
        raw_delta *= salience_scale * relationship_modifier

        # Global event gain — keeps chatbot-scale inputs sub-physiological.
        # The register-shift impulse is added after, so a breakup is not
        # shrunk by the same gain that keeps small talk small.
        raw_delta *= EVENT_GAIN
        raw_delta += impulse

        # PFC frontend regulation
        neuroticism = big5.get("neuroticism", 50.0)
        raw_delta = _apply_pfc_regulation(raw_delta, p, neuroticism)

        # Source-side negative feedback (autoreceptor headroom)
        current_norm = _get_normalized(state, chem)
        ceiling = p["feedback_ceiling"]
        headroom = max(0.0, ceiling * 10.0 - current_norm)
        if headroom <= 0 and raw_delta > 0:
            continue
        if raw_delta > 0:
            feedback_scale = headroom / (ceiling * 10.0)
            raw_delta *= feedback_scale

        # Gain bias from Big 5
        gain = _compute_gain(chem, big5)
        raw_delta *= gain

        # Receptor sensitivity (habituation / upregulation)
        lvl = state.levels.get(chem)
        if lvl:
            raw_delta *= lvl.sensitivity

        # Convert normalized delta to nM and apply to phasic
        norm_max = p["normalization_max"]
        delta_nM = raw_delta * norm_max / 10.0

        if lvl:
            before = lvl.phasic
            lvl.phasic = max(0.0, lvl.phasic + delta_nM)
            # Cap total so a burst of messages cannot exceed phys max
            max_total = norm_max * CHEMICAL_TOTAL_CAP_MULT
            excess = (lvl.tonic + lvl.phasic) - max_total
            if excess > 0:
                lvl.phasic = max(0.0, lvl.phasic - excess)
            actual = lvl.phasic - before
            if abs(actual) >= 0.001:
                applied[chem] = round(actual, 3)

    return applied


def _apply_pfc_regulation(raw_delta: float, params: dict, neuroticism: float) -> float:
    """Apply PFC frontend regulation. High neuroticism weakens regulation."""
    reg_key = params.get("pfc_regulation", "none")
    base_factor = PFC_REGULATION_BASE.get(reg_key, 1.0)
    if base_factor >= 1.0:
        return raw_delta
    # Neuroticism weakens regulation: N=100 → full regulation removed; N=0 → full
    n_frac = neuroticism / 100.0
    effective_factor = base_factor + (1.0 - base_factor) * n_frac
    return raw_delta * effective_factor


def _compute_gain(chemical: str, big5: dict[str, float]) -> float:
    """Compute phasic gain multiplier from Big 5 for this chemical."""
    gain = 1.0
    for trait, biases in BIG5_GAIN_BIAS.items():
        chem_bias = biases.get(chemical, 0.0)
        if chem_bias == 0.0:
            continue
        trait_val  = big5.get(trait, 50.0)
        trait_frac = (trait_val - 50.0) / 50.0
        gain += chem_bias * trait_frac
    return max(0.1, gain)


def _build_effective_weights(big5: dict[str, float]) -> dict[str, dict[str, float]]:
    """Apply Big 5 axis biases to base axis weights. Cached per call."""
    result: dict[str, dict[str, float]] = {}
    for chem, p in CHEMICAL_PARAMS.items():
        base = dict(p.get("axis_weights", {}))
        if not base:
            continue
        for trait, chem_biases in BIG5_AXIS_BIAS.items():
            axis_biases = chem_biases.get(chem, {})
            if not axis_biases:
                continue
            trait_val  = big5.get(trait, 50.0)
            trait_frac = (trait_val - 50.0) / 50.0
            for axis, scale in axis_biases.items():
                if axis in base:
                    base[axis] += base[axis] * scale * trait_frac
                else:
                    base[axis]  = scale * trait_frac * 0.3  # base if axis not present
        result[chem] = base
    return result
