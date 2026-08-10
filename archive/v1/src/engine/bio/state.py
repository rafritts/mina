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

from src.engine.bio.defaults import (
    chemical_defaults,
    neuroendocrine_defaults,
    immune_defaults,
    pain_defaults,
    body_defaults,
    neuroplasticity_defaults,
    CHEMICAL_DEFAULTS,
)
from src.engine.bio.migration import _migrate_v1_to_v2, migrate_v2_to_v3, migrate_v3_to_v4
from src.engine.constants import ADENOSINE_SLEEP_DRIVE_MIN, ADENOSINE_SLEEP_DRIVE_DIVISOR


@dataclass
class BiologicalState:
    schema_version: int = 4
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

    # ── SPEC-29: stimulus processing / habituation / sensitization ────────────
    # stimulus_window: rolling recent stimuli for content novelty comparison.
    # Each entry: {"embedding": [...], "ts": float, "summary": str}
    stimulus_window: list = field(default_factory=list)

    # sensitization: single-source record (Mina is single-user).
    # {"contact_count": int, "accumulated_valence": float,
    #  "sensitization_level": float, "last_contact_ts": float, "first_contact_ts": float}
    sensitization: dict = field(default_factory=dict)

    # SPEC-46: session satiation — within-session reactivity multiplier state.
    # {"session_contact_count": float, "last_contact_ts": float, "session_start_ts": float}
    # Reset on sleep wake. Partial exponential recovery (2h half-life) during gaps.
    session_satiation: dict = field(default_factory=dict)

    # secretion_queue: pending neurotransmitter drip entries processed by advance().
    # Each entry: {"chemical": str, "remaining": float, "rate_per_sim_hour": float, "posted_at": float}
    secretion_queue: list = field(default_factory=list)

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
        """
        Sleep pressure in AU (0–100). Derived from body["adenosine"].
        adenosine 20 nmol/L → 0 AU (fully rested)
        adenosine 80 nmol/L → 100 AU (exhausted)

        Adenosine receptor sensitivity modulates the effective sleep signal:
        caffeine blocks A1/A2A so adenosine builds but doesn't register as sleepiness.
        """
        raw = (self.body["adenosine"] - ADENOSINE_SLEEP_DRIVE_MIN) / ADENOSINE_SLEEP_DRIVE_DIVISOR
        raw = min(100.0, max(0.0, raw))

        # Caffeine receptor block: A1/A2A sensitivity is transiently reduced
        # while caffeine is active. Read directly from substances to avoid circular imports.
        caffeine_level = self.substances.get("caffeine", {}).get("level", 0.0)
        a1_sens  = self.receptor_sensitivity.get("adenosine", {}).get("A1",  1.0)
        a2a_sens = self.receptor_sensitivity.get("adenosine", {}).get("A2A", 1.0)
        if caffeine_level > 0.5:
            # Block scales with dose: at 100 level, full 0.7× block
            block_factor = 1.0 - 0.3 * min(1.0, caffeine_level / 100.0)
            a1_sens  = a1_sens  * block_factor
            a2a_sens = a2a_sens * block_factor

        mean_receptor_sens = (a1_sens + a2a_sens) / 2.0
        return raw * mean_receptor_sens

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BiologicalState":
        version = d.get("schema_version", 1)
        if version < 2:
            d = _migrate_v1_to_v2(d)
        if d.get("schema_version", 2) < 3:
            d = migrate_v2_to_v3(d)
        if d.get("schema_version", 3) < 4:
            d = migrate_v3_to_v4(d)
        known = set(cls.__dataclass_fields__)
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Delta application (from subconscious / encoder)
# ---------------------------------------------------------------------------

def apply_deltas(s: BiologicalState, deltas: dict) -> BiologicalState:
    """
    Apply subconscious-issued delta dict to state. Clamps all values.

    Valid delta keys:
      - Any key in REGISTRY (chemicals dict), except sleep_pressure (see below)
      - "sleep_pressure": redirected to body["adenosine"] (Δadenonsine = Δsp × 0.6)
      - "anandamide": redirected to body["anandamide"] (SPEC-30: body-stored endocannabinoid)
      - "prolactin": redirected to neuroendocrine["prolactin"] (SPEC-30: satiation)
      - "tolerance" dict: substance tolerance scalars
    """
    from src.engine.chem.registry import REGISTRY
    from src.engine.chem.units import clamp_chemical

    _chemical_fields = set(REGISTRY.keys()) - {"sleep_pressure", "anandamide"}

    # Neuroendocrine keys the encoder is allowed to write (narrow whitelist)
    _neuroendocrine_fields = {"prolactin"}

    for key, val in deltas.items():
        if key == "sleep_pressure":
            # SPEC-21: sleep_pressure is now derived from body["adenosine"].
            # Translate: Δadenonsine = Δsleep_pressure × 0.6
            current_a = s.body.get("adenosine", 38.0)
            s.body["adenosine"] = max(15.0, min(100.0, current_a + float(val) * 0.6))
        elif key == "anandamide":
            # SPEC-30: anandamide is body-stored; clamp to physiological bounds (0–15 nM)
            current = s.body.get("anandamide", 1.5)
            s.body["anandamide"] = max(0.0, min(15.0, current + float(val)))
        elif key in _neuroendocrine_fields:
            # SPEC-30: narrow neuroendocrine write path for prolactin (satiation)
            current = s.neuroendocrine.get(key, 0.0)
            s.neuroendocrine[key] = max(0.0, current + float(val))
        elif key in _chemical_fields:
            current = s.chemicals.get(key, CHEMICAL_DEFAULTS.get(key, 0.0))
            s.chemicals[key] = clamp_chemical(key, current + float(val))
        elif key == "tolerance" and isinstance(val, dict):
            for substance, delta in val.items():
                current = s.tolerance.get(substance, 0.0)
                s.tolerance[substance] = max(0.0, min(1.0, current + float(delta)))
    return s


def log_state(s: BiologicalState) -> None:
    # Deferred import to avoid circular dependency (psych.derived → bio.state)
    from src.engine.psych.derived import derived
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
