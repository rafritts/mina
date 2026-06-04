"""
Chemistry function — deterministic mapping from encoder output to Class 1 deltas.

Encoder output → axis activations (0-10 integers) → weighted sum per chemical
→ source-side negative feedback → PFC frontend regulation → apply delta.

Only touches Class 1 chemicals (DA, 5-HT, NE, epinephrine). Class 2/3/4 are
tick-only and never receive direct encoder deltas. The absence of axis_weights
in a chemical's params entry is the documentation of this.

Salience floor: axis values ≤ 2 are treated as zero (noise suppression).
"""
from __future__ import annotations

import math

from .state import ChemicalState
from .params import CHEMICAL_PARAMS, PFC_REGULATION_BASE, BIG5_GAIN_BIAS, BIG5_AXIS_BIAS

_SALIENCE_FLOOR = 2  # axis values ≤ this are ignored


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
) -> None:
    """
    Apply encoder axis activations as Class 1 phasic deltas.
    Mutates state.levels[chemical].phasic in place.

    encoder_output: {
      "salience": 0-10, "threat": 0-10, ...,
      "directed_at_mina": bool,
      "register_shift": bool, "expected_magnitude": 0-10,
      "channel": "dialogue" | "action"
    }
    big5: {"neuroticism": 65, "extraversion": 48, ...}
    relationship_modifier: multiplier from relationship state (bonding dimension)
    """
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

        if abs(raw_delta) < 0.01:
            continue

        # Scale by salience and relationship modifier
        salience_scale = encoder_output.get("salience", 5) / 5.0
        raw_delta *= salience_scale * relationship_modifier

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

        # Convert normalized delta to nM and apply to phasic
        norm_max = p["normalization_max"]
        delta_nM = raw_delta * norm_max / 10.0

        lvl = state.levels.get(chem)
        if lvl:
            lvl.phasic = max(0.0, lvl.phasic + delta_nM)


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
