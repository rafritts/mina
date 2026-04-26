"""ChemicalProfile and Interaction dataclasses — shared chemical architecture types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Optional


@dataclass
class Interaction:
    """A cross-chemical effect: when source crosses threshold, affect target at rate."""
    target: str
    condition: str              # "above" | "below"
    threshold: float            # in source chemical's real units
    rate_per_hour: float        # in TARGET chemical's real units per sim-hour
    description: str            # documentation only


@dataclass
class ChemicalProfile:
    name: str
    display_name: str
    unit: str

    resting_baseline: float               # homeostatic target (real units); 0.0 = no baseline
    approach_rate: float                  # fraction of gap closed per sim-hour; 0.0 = special case

    baseline_fn: Optional[Callable] = None  # signature: (hour: float, ctx: dict) -> float
                                             # overrides resting_baseline when dynamic

    resting_low: float   = 0.0           # below this = abnormally low
    resting_high: float  = 0.0           # above this = elevated
    critical_low: float  = 0.0           # below this = clinically dangerous
    critical_high: float = 0.0           # above this = clinically dangerous / physics max

    display_min: float   = 0.0           # bar chart bottom
    display_max: float   = 0.0           # bar chart top

    # Saturation ceilings for subconscious-issued deltas (not substances)
    soft_ceiling: Optional[float] = None     # scaling begins above this
    hard_ceiling: Optional[float] = None     # positive deltas clamped to zero above this

    # Saturation floors — mirror of ceilings for negative deltas
    soft_floor: Optional[float] = None      # dampening begins below this
    hard_floor: Optional[float] = None      # negative deltas clamped to zero below this

    interactions: list[Interaction] = field(default_factory=list)
    labels: list[tuple[float, str, str]] = field(default_factory=list)
    # Each entry: (upper_bound_exclusive, label_name, implication)

    # --- SPEC-53 additions ---

    # Compartment: which side of the blood-brain barrier this chemical lives in.
    # "bloodstream" = plasma/peripheral; "synaptic" = CNS, behind BBB.
    # Metadata only in this spec; used by SPEC-54 pool separation.
    pool: Literal["bloodstream", "synaptic"] = "bloodstream"

    # Clearance model determines how the engine advances this chemical each tick.
    #   "exponential"  — hepatic/enzymatic first-order kinetics: C(t) = C0 * 0.5^(t/t½)
    #   "gap_closure"  — homeostatic reuptake/regulation: C += (target - C) * rate * Δt
    #   "formula"      — circadian or forced value: direct assignment from baseline_fn
    clearance: Literal["exponential", "gap_closure", "formula"] = "gap_closure"

    # Required when clearance == "exponential": half-life in minutes (plasma).
    plasma_half_life: Optional[float] = None

    # Threshold-triggered state descriptions collected by the decoder.
    # Each entry: (threshold, tag, description) — active when concentration >= threshold.
    notes: list[tuple[float, str, str]] = field(default_factory=list)

    # Gaussian noise applied after clearance each tick (std dev in native units).
    # 0.0 = no noise. Scaled by global noise_scale in the engine.
    noise_sigma: float = 0.0
