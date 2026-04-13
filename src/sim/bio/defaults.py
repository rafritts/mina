"""
Default starting values for all biological state tiers.

chemical_defaults() is overrideable by config.json neurochemical_baselines.
All other defaults are fixed at canonical physiological resting values.
"""
from __future__ import annotations

from ...infra.config import load_config


def chemical_defaults() -> dict[str, float]:
    """Base defaults, overrideable by config.json neurochemical_baselines."""
    defaults = {
        "cortisol":        250.0,   # nmol/L — circadian midpoint
        "norepinephrine":  200.0,   # pg/mL
        "dopamine":         80.0,   # pg/mL
        "serotonin":        22.0,   # ng/mL
        "oxytocin":          4.0,   # pg/mL — no bond floor
        "endorphins":       12.0,   # pg/mL
        "acetylcholine":    38.0,   # nmol/L
        "melatonin":         5.0,   # pg/mL — daytime low
        "glucose":          85.0,   # mg/dL — normal fasting
        "hydration":        62.0,   # % TBW
        # SPEC-21: sleep_pressure removed from chemicals; now derived from body["adenosine"].
        # gaba/glutamate added as first-class chemicals.
        "gaba":              3.0,   # µmol/L — CSF proxy resting baseline
        "glutamate":         4.0,   # µmol/L — CSF proxy resting baseline
    }
    try:
        nb = load_config().get("neurochemical_baselines", {})
        if "oxytocin_resting" in nb:
            defaults["oxytocin"] = float(nb["oxytocin_resting"])
        if "serotonin_resting" in nb:
            defaults["serotonin"] = float(nb["serotonin_resting"])
    except Exception:
        pass
    return defaults


def neuroendocrine_defaults() -> dict[str, float]:
    return {
        # HPA axis intermediaries
        "crh":              30.0,   # pg/mL  — CRH from hypothalamus (normal: 10-50)
        "acth":             25.0,   # pg/mL  — ACTH from pituitary (normal: 10-60)
        # Thyroid axis
        "tsh":               2.0,   # mIU/L  — thyroid stimulating hormone (normal: 0.4-4.0)
        "t4":                8.0,   # µg/dL  — inactive (normal: 5-12)
        "t3":              120.0,   # ng/dL  — active (normal: 80-200)
        # Sex hormones (female baseline, follicular phase)
        "estradiol":       100.0,   # pg/mL  — (normal: 20-350, varies with cycle)
        "progesterone":      0.5,   # ng/mL  — (normal: 0.1-25, varies with cycle)
        "testosterone":     40.0,   # ng/dL  — (female normal: 15-70)
        # Metabolic hormones
        "insulin":           5.0,   # µIU/mL — (normal fasting: 2-20)
        "glucagon":         80.0,   # pg/mL  — (normal: 50-150)
        "leptin":           15.0,   # ng/mL  — satiety (normal: 4-25 female)
        "ghrelin":         400.0,   # pg/mL  — hunger (normal fasting: 300-600)
        # Social/bonding hormones
        "vasopressin":       2.0,   # pg/mL  — ADH / social bonding (normal: 1-5)
        "prolactin":         8.0,   # ng/mL  — (normal: 2-29)
        # Other
        "growth_hormone":    1.0,   # ng/mL  — pulsatile (normal: 0-10)
        "dhea":            150.0,   # µg/dL  — anti-stress (female normal: 35-430)
        # Wake-promoting
        "orexin":          300.0,   # pg/mL  — CSF proxy (normal: 200-400)
    }


def immune_defaults() -> dict[str, float]:
    return {
        "il1b":              2.0,   # pg/mL  — IL-1β (normal: <5)
        "il6":               3.0,   # pg/mL  — IL-6 (normal: <10)
        "tnf_alpha":         3.0,   # pg/mL  — TNF-α (normal: <8)
        "crp":               0.5,   # mg/L   — C-reactive protein (normal: <1 low-risk)
        "il10":             10.0,   # pg/mL  — anti-inflammatory IL-10 (normal: 5-20)
        "inflammation_index": 0.0,  # 0-100 AU, derived each tick
    }


def pain_defaults() -> dict[str, float]:
    return {
        "substance_p":           30.0,  # pg/mL  — CSF proxy (normal: 20-60)
        "pge2":                  80.0,  # pg/mL  — prostaglandin E2 (normal: 50-200)
        "central_sensitization":  0.0,  # 0-100 AU — builds with chronic pain
        "pain_intensity":          0.0,  # 0-100 AU — current subjective pain signal
    }


def body_defaults(sleep_pressure_au: float = 30.0) -> dict[str, float]:
    # Adenosine initialized from sleep_pressure for v2→v3 migration:
    # sleep_pressure = (adenosine - 20) * (100/60)  →  adenosine = sp * 0.6 + 20
    adenosine = sleep_pressure_au * 0.6 + 20.0
    return {
        "adenosine":   adenosine,  # nmol/L  — real sleep molecule (normal awake: 20-40)
        "anandamide":       1.5,   # nM      — endocannabinoid 1 (normal: 0.5-5)
        "two_ag":           8.0,   # nM      — endocannabinoid 2 (normal: 5-20)
        "core_temp":       37.0,   # °C      — body temperature (normal: 36.5-37.2)
    }


def neuroplasticity_defaults() -> dict[str, float]:
    return {
        "bdnf":                  9000.0,  # pg/mL  — serum proxy ~9 ng/mL (normal: 6-12 ng/mL)
        "synaptic_potentiation":   50.0,  # 0-100 AU — LTP-like synaptic strength
        "allostatic_load":          0.0,  # 0-100 AU — cumulative biological stress burden
    }


# Module-level constant — used by advance() and apply_deltas() for defaults lookup.
# Computed at import time; caller code treats this as a read-only snapshot.
CHEMICAL_DEFAULTS: dict[str, float] = chemical_defaults()
