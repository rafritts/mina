"""ChemicalProfile and Interaction dataclasses — shared chemical architecture types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


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

    interactions: list[Interaction] = field(default_factory=list)
    labels: list[tuple[float, str, str]] = field(default_factory=list)
    # Each entry: (upper_bound_exclusive, label_name, implication)
