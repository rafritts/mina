"""Physical stats — body measurements and derived biological constants.

Values come from config.json `physical_stats`. Derived quantities are
computed at call time (with a 60s cache) and are pure functions of config.

Formulas used:
  Widmark r  — body-fat-adjusted via total body water fraction
               TBW = (lean_mass × 0.73) + (fat_mass × 0.12)
               r = TBW / weight_kg
  BAC        — Widmark: grams_ethanol / (weight_kg × r × 10)  [g/dL]
  BMR        — Mifflin-St Jeor (female):
               10×weight_kg + 6.25×height_cm − 5×age − 161   [kcal/day]
  Blood vol  — Nadler (female):
               0.3561×height_m³ + 0.03308×weight_kg + 0.1833 [L]
"""
from __future__ import annotations

import time as _time

# ---------------------------------------------------------------------------
# Defaults (Mina's canonical measurements from identity/CUSTOMIZATION.md)
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "age":          24,
    "height_cm":    170.18,   # 5'7"
    "weight_kg":    63.50,    # 140 lbs
    "body_fat_pct": 25.0,
}

# One "dose" of alcohol in the substance system (level=100) = 1 US standard drink
ALCOHOL_GRAMS_PER_DOSE = 14.0   # g ethanol per standard drink

_cache: dict = {}
_cache_ts: float = 0.0
_CACHE_TTL = 60.0


def _stats() -> dict:
    """Return physical stats from config, with defaults as fallback. Cached 60s."""
    global _cache, _cache_ts
    now = _time.monotonic()
    if now - _cache_ts < _CACHE_TTL and _cache:
        return _cache
    try:
        from src.infra.config import load_config
        cfg = load_config().get("physical_stats", {})
        _cache = {**_DEFAULTS, **cfg}
    except Exception:
        _cache = dict(_DEFAULTS)
    _cache_ts = now
    return _cache


def get_physical_stats() -> dict:
    """Return the full physical stats dict (age, height_cm, weight_kg, body_fat_pct)."""
    return _stats()


def widmark_r() -> float:
    """
    Body-fat-adjusted Widmark distribution factor (r).

    Standard female value ≈ 0.55; lean athletes approach 0.60, higher-BF ~0.50.
    At Mina's 25% BF: r ≈ 0.578 (close to the textbook female value).
    """
    s = _stats()
    wt  = s["weight_kg"]
    bf  = s["body_fat_pct"] / 100.0
    lean_mass = wt * (1.0 - bf)
    fat_mass  = wt * bf
    tbw = lean_mass * 0.73 + fat_mass * 0.12     # total body water, litres
    return tbw / wt


def bac_from_level(alcohol_level: float) -> float:
    """
    Convert substance engine alcohol level (0–100) to Blood Alcohol Concentration (g/dL).

    level=100 represents one full dose (1 standard drink = 14g ethanol).
    BAC decays proportionally as the level decays.
    """
    s   = _stats()
    r   = widmark_r()
    wt  = s["weight_kg"]
    grams = (alcohol_level / 100.0) * ALCOHOL_GRAMS_PER_DOSE
    return grams / (wt * r * 10.0)


def bmr_kcal() -> float:
    """
    Basal metabolic rate in kcal/day (Mifflin-St Jeor, female).
    Used to inform glucose burn rate in the metabolic subsystem.
    """
    s = _stats()
    return (10.0 * s["weight_kg"]
            + 6.25 * s["height_cm"]
            - 5.0  * s["age"]
            - 161.0)


def blood_volume_L() -> float:
    """
    Estimated total blood volume in litres (Nadler formula, female).
    Useful as a concentration denominator for future substance models.
    """
    s = _stats()
    h = s["height_cm"] / 100.0   # metres
    return 0.3561 * (h ** 3) + 0.03308 * s["weight_kg"] + 0.1833
