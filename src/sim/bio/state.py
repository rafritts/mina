"""
BiologicalState v3 — single source of truth for Mina's biology.

Schema tiers:
  Tier 1: chemicals       — first-order neurotransmitters + metabolic markers (real units)
  Tier 2: neuroendocrine  — HPA cascade, thyroid, sex hormones, metabolic hormones
  Tier 3: immune          — cytokines, inflammation index
  Tier 4: pain            — nociception, central sensitization
  Tier 5: body            — adenosine, endocannabinoids, core temperature
  Tier 6: neuroplasticity — BDNF, allostatic load, synaptic potentiation
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from src.sim.bio.defaults import (
    chemical_defaults,
    neuroendocrine_defaults,
    immune_defaults,
    pain_defaults,
    body_defaults,
    neuroplasticity_defaults,
    CHEMICAL_DEFAULTS,
)
from src.sim.bio.migration import _migrate_v1_to_v2, migrate_v2_to_v3


@dataclass
class BiologicalState:
    schema_version: int = 3
    last_updated: float = field(default_factory=time.time)

    # ── TIER 1: First-order chemicals (real physiological units) ───────────────
    # Keys match REGISTRY. Units documented in src/sim/chem/registry.py.
    # sleep_pressure kept here for v2 backward compat; SPEC-21 migrates it to body.adenosine.
    chemicals: dict = field(default_factory=chemical_defaults)

    # ── TIER 2: Neuroendocrine cascade intermediaries ──────────────────────────
    neuroendocrine: dict = field(default_factory=neuroendocrine_defaults)

    # ── TIER 3: Immune markers ─────────────────────────────────────────────────
    immune: dict = field(default_factory=immune_defaults)

    # ── TIER 4: Pain state ─────────────────────────────────────────────────────
    pain: dict = field(default_factory=pain_defaults)

    # ── TIER 5: Body state ─────────────────────────────────────────────────────
    body: dict = field(default_factory=body_defaults)

    # ── TIER 6: Neuroplasticity markers ───────────────────────────────────────
    neuroplasticity: dict = field(default_factory=neuroplasticity_defaults)

    # ── Receptor sensitivity ───────────────────────────────────────────────────
    # receptor_sensitivity[nt_name][receptor_type] = multiplier (0.2–2.0, 1.0 = normal)
    receptor_sensitivity: dict = field(default_factory=dict)

    # ── HPA cascade delay queue ────────────────────────────────────────────────
    # Pending delayed effects: list of {"target": str, "delta": float, "fires_at": float}
    cascade_queue: list = field(default_factory=list)

    # ── Menstrual cycle ────────────────────────────────────────────────────────
    cycle_day: int = 1  # 1-28; drives estradiol/progesterone baseline_fn

    # ── Context queue ─────────────────────────────────────────────────────────
    # Shared memory context written by encoder, read and drained by decoder.
    # Each entry: {"text": str, "source": "rag"|"kag", "query": str,
    #              "added_at": float, "ttl_seconds": float}
    context_queue: list = field(default_factory=list)

    # ── Existing v2 fields ────────────────────────────────────────────────────
    tolerance: dict = field(default_factory=dict)
    substances: dict = field(default_factory=dict)
    sleeping: bool = False
    sleep_start: Optional[float] = None
    sleep_expected_wake: Optional[float] = None
    encoder_momentum: dict = field(default_factory=dict)

    # ---------------------------------------------------------------------------
    # Convenience read-only accessors — allow old call sites to work
    # ---------------------------------------------------------------------------

    @property
    def cortisol(self) -> float:
        return self.chemicals.get("cortisol", CHEMICAL_DEFAULTS["cortisol"])

    @property
    def norepinephrine(self) -> float:
        return self.chemicals.get("norepinephrine", CHEMICAL_DEFAULTS["norepinephrine"])

    @property
    def dopamine(self) -> float:
        return self.chemicals.get("dopamine", CHEMICAL_DEFAULTS["dopamine"])

    @property
    def serotonin(self) -> float:
        return self.chemicals.get("serotonin", CHEMICAL_DEFAULTS["serotonin"])

    @property
    def oxytocin(self) -> float:
        return self.chemicals.get("oxytocin", CHEMICAL_DEFAULTS["oxytocin"])

    @property
    def endorphins(self) -> float:
        return self.chemicals.get("endorphins", CHEMICAL_DEFAULTS["endorphins"])

    @property
    def acetylcholine(self) -> float:
        return self.chemicals.get("acetylcholine", CHEMICAL_DEFAULTS["acetylcholine"])

    @property
    def melatonin(self) -> float:
        return self.chemicals.get("melatonin", CHEMICAL_DEFAULTS["melatonin"])

    @property
    def glucose(self) -> float:
        return self.chemicals.get("glucose", CHEMICAL_DEFAULTS["glucose"])

    @property
    def hydration(self) -> float:
        return self.chemicals.get("hydration", CHEMICAL_DEFAULTS["hydration"])

    @property
    def sleep_pressure(self) -> float:
        # v2 backward compat: reads from chemicals["sleep_pressure"].
        # SPEC-21 will migrate this to derive from body["adenosine"].
        return self.chemicals.get("sleep_pressure", CHEMICAL_DEFAULTS["sleep_pressure"])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BiologicalState":
        version = d.get("schema_version", 1)
        if version < 2:
            d = _migrate_v1_to_v2(d)
        if d.get("schema_version", 2) < 3:
            d = migrate_v2_to_v3(d)
        known = set(cls.__dataclass_fields__)
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Delta application (from subconscious / encoder)
# ---------------------------------------------------------------------------

def apply_deltas(s: BiologicalState, deltas: dict) -> BiologicalState:
    """
    Apply subconscious-issued delta dict to state. Clamps all values.

    Valid delta keys: any key in REGISTRY (chemicals), plus "tolerance" dict.
    sleep_pressure is a valid key — maps directly to chemicals["sleep_pressure"]
    until SPEC-21 migrates it to body["adenosine"].
    """
    from src.sim.chem.registry import REGISTRY
    from src.sim.chem.units import clamp_chemical

    _delta_fields = set(REGISTRY.keys())

    for key, val in deltas.items():
        if key in _delta_fields:
            current = s.chemicals.get(key, CHEMICAL_DEFAULTS.get(key, 0.0))
            s.chemicals[key] = clamp_chemical(key, current + float(val))
        elif key == "tolerance" and isinstance(val, dict):
            for substance, delta in val.items():
                current = s.tolerance.get(substance, 0.0)
                s.tolerance[substance] = max(0.0, min(1.0, current + float(delta)))
    return s


def log_state(s: BiologicalState) -> None:
    # Deferred import to avoid circular dependency (psych.derived → bio.state)
    from src.sim.psych.derived import derived
    try:
        from log import log
    except ImportError:
        return

    d = derived(s)
    so = d["second_order"]
    to = d["third_order"]
    log("STATE",
        f"sleep_p={s.sleep_pressure:.1f}AU glucose={s.glucose:.0f}mg/dL "
        f"hydration={s.hydration:.1f}%TBW cortisol={s.cortisol:.0f}nmol/L "
        f"dopamine={s.dopamine:.0f}pg/mL serotonin={s.serotonin:.1f}ng/mL "
        f"norepi={s.norepinephrine:.0f}pg/mL oxytocin={s.oxytocin:.1f}pg/mL "
        f"endorphins={s.endorphins:.0f}pg/mL ach={s.acetylcholine:.1f}nmol/L "
        f"melatonin={s.melatonin:.0f}pg/mL sleeping={s.sleeping}"
    )
    log("DERIV",
        f"energy={so['energy']} clarity={so['cognitive_clarity']} "
        f"hedonic={so['hedonic_tone']} warmth={so['social_warmth']} "
        f"arousal={so['arousal']} valence={so['mood_valence']}"
    )
    log("THIRD",
        f"anxiety={to['anxiety']} depression={to['depression']} "
        f"boredom={to['boredom']} loneliness={to['loneliness']} flow={to['flow']}"
    )
