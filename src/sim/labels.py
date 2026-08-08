"""
Chemistry display labels — SPEC-63 Phase 3.

Canonical chip names for Control / admin. Driven by decoder-scale
normalized 0–10 and gap (vs setpoint + circadian target), never by v1
pg/mL plasma tables.

Kinds (UI shorthand only — not tonic/phasic, not textbook neuroscience):
  tone   — monoamine mood floor (DA, 5-HT, NE)
  surge  — floor-is-normal-low (OT, epi, endorphins)
  sleep  — adenosine sleep pressure
  clock  — melatonin absolute phase; cortisol gap-aware stress
  generic — other chems: gap bands only
"""
from __future__ import annotations

import time
from typing import TypedDict

from .params import CHEMICAL_PARAMS, SLEEP_ENTER_ADENOSINE
from .tick import _circadian_offset, _hour_of_day


class LabelResult(TypedDict):
    name: str
    color: str  # success | warning | error | info | neutral
    implication: str


# ── Classification ────────────────────────────────────────────────────────────

TONE = frozenset({"dopamine", "serotonin", "norepinephrine"})
SURGE = frozenset({"oxytocin", "epinephrine", "endorphins"})
SLEEP = frozenset({"adenosine"})
# Melatonin: absolute norm (phase). Cortisol: gap-first (stress vs clock).
CLOCK_ABSOLUTE = frozenset({"melatonin"})
CLOCK_GAP = frozenset({"cortisol"})


def _norm10(value_nM: float, norm_max: float) -> float:
    if norm_max <= 0:
        return 0.0
    return max(0.0, value_nM / norm_max * 10.0)


def _target_nM(name: str, setpoint: float, hour: float | None = None) -> float:
    """Allostatic setpoint + current circadian offset (0 if not clock-driven)."""
    if hour is None:
        hour = _hour_of_day(time.time())
    return setpoint + _circadian_offset(name, hour)


def display_unit(name: str) -> str:
    """Working unit string for API/UI. Melatonin shares the sim's working scale."""
    # Sim dynamics treat all of these as the same working concentration space.
    # Historical param comments may say pg/mL; display matches what the engine uses.
    if name in CHEMICAL_PARAMS:
        return "nM"
    return "nM"


def display_range(name: str) -> dict[str, float | str] | None:
    """Slider min/max from CHEMICAL_PARAMS.normalization_max."""
    p = CHEMICAL_PARAMS.get(name)
    if not p:
        return None
    return {
        "min": 0.0,
        "max": float(p["normalization_max"]),
        "unit": display_unit(name),
    }


# ── Band helpers ──────────────────────────────────────────────────────────────

def _tone(name: str, gap: float, norm: float) -> LabelResult:
    # Absolute floor: collapsed even if setpoint also crushed
    if norm < 0.5:
        if name == "dopamine":
            return {
                "name": "ANHEDONIC",
                "color": "error",
                "implication": "Drive floor collapsed — nothing feels worth doing",
            }
        if name == "serotonin":
            return {
                "name": "SEVERELY LOW",
                "color": "error",
                "implication": "Mood floor gone — fragile, raw",
            }
        return {
            "name": "SEDATED",
            "color": "error",
            "implication": "Arousal floor collapsed — heavy and slow",
        }

    if gap <= -3.0:
        if name == "dopamine":
            return {
                "name": "NO DRIVE",
                "color": "error",
                "implication": "Well below her baseline wanting",
            }
        if name == "serotonin":
            return {
                "name": "DYSPHORIC",
                "color": "error",
                "implication": "Below her mood floor — negative bias",
            }
        return {
            "name": "SEDATED",
            "color": "warning",
            "implication": "Well below her resting alertness",
        }

    if gap <= -1.5:
        if name == "dopamine":
            return {
                "name": "LOW SEEKING",
                "color": "warning",
                "implication": "Flat motivation relative to her baseline",
            }
        if name == "serotonin":
            return {
                "name": "INSECURE",
                "color": "warning",
                "implication": "Shaky mood floor — easily hurt",
            }
        return {
            "name": "RELAXED",
            "color": "success",
            "implication": "Calm, low urgency — still in healthy band",
        }

    if abs(gap) < 1.5:
        if name == "dopamine":
            return {
                "name": "BASELINE",
                "color": "success",
                "implication": "Normal drive — things feel worth doing",
            }
        if name == "serotonin":
            return {
                "name": "NEUTRAL",
                "color": "success",
                "implication": "Even keel — her ordinary mood floor",
            }
        return {
            "name": "CALM ALERT",
            "color": "success",
            "implication": "Present and clear — ordinary resting NE",
        }

    if gap < 3.0:
        if name == "dopamine":
            return {
                "name": "ACTIVE SEEKING",
                "color": "info",
                "implication": "Energized — pursuing something",
            }
        if name == "serotonin":
            return {
                "name": "SECURE",
                "color": "success",
                "implication": "Stable, grounded above baseline",
            }
        return {
            "name": "FOCUSED",
            "color": "success",
            "implication": "Sharp edge — locked in",
        }

    if gap < 5.0:
        if name == "dopamine":
            return {
                "name": "HIGH DRIVE",
                "color": "warning",
                "implication": "Intense focus, compulsive pull",
            }
        if name == "serotonin":
            return {
                "name": "VERY STABLE",
                "color": "success",
                "implication": "Resilient mood floor",
            }
        return {
            "name": "HEIGHTENED",
            "color": "warning",
            "implication": "Urgency rising — hyperaware",
        }

    if name == "dopamine":
        return {
            "name": "COMPULSIVE",
            "color": "error",
            "implication": "Can't stop — no off switch",
        }
    if name == "serotonin":
        return {
            "name": "FLOODED",
            "color": "success",
            "implication": "Profoundly serene — almost sedated",
        }
    return {
        "name": "OVERDRIVE",
        "color": "error",
        "implication": "Fight-or-flight territory",
    }


def _surge(name: str, gap: float, norm: float) -> LabelResult:
    """Floor-is-normal-low. gap≈0 → RESTING, never isolation/relationship ladder."""
    if gap <= -2.0:
        return {
            "name": "LOW TONE",
            "color": "warning",
            "implication": "Below her resting floor for this chemical",
        }
    if abs(gap) < 1.5:
        if name == "oxytocin":
            return {
                "name": "RESTING",
                "color": "success",
                "implication": "Ordinary resting OT — no active bond surge (not isolation)",
            }
        if name == "epinephrine":
            return {
                "name": "RESTING",
                "color": "success",
                "implication": "No acute adrenaline surge",
            }
        return {
            "name": "BASELINE",
            "color": "neutral",
            "implication": "No particular glow — ordinary resting buffer",
        }

    if gap < 3.0:
        if name == "oxytocin":
            return {
                "name": "WARMING",
                "color": "info",
                "implication": "Mild bonding surge above her floor",
            }
        if name == "epinephrine":
            return {
                "name": "MILD AROUSAL",
                "color": "info",
                "implication": "Light adrenaline lift",
            }
        return {
            "name": "MILD WARMTH",
            "color": "info",
            "implication": "Quiet satisfaction — pleasant background hum",
        }

    if gap < 5.0:
        if name == "oxytocin":
            return {
                "name": "CONNECTED",
                "color": "success",
                "implication": "Clear bonding surge — warmth online",
            }
        if name == "epinephrine":
            return {
                "name": "SURGE",
                "color": "warning",
                "implication": "Acute fight-flight engagement",
            }
        return {
            "name": "PLEASURE",
            "color": "success",
            "implication": "Genuinely good — body buffer high",
        }

    if gap < 7.0:
        if name == "oxytocin":
            return {
                "name": "DEEP SURGE",
                "color": "success",
                "implication": "Strong sustained bonding chemistry",
            }
        if name == "epinephrine":
            return {
                "name": "ACUTE SURGE",
                "color": "error",
                "implication": "Near-max adrenaline",
            }
        return {
            "name": "HIGH",
            "color": "success",
            "implication": "Euphoric lift — pain doesn't reach",
        }

    return {
        "name": "SATURATED",
        "color": "warning",
        "implication": "At working ceiling for this surge chemical",
    }


def _sleep_pressure(norm: float) -> LabelResult:
    """Absolute normalized bands; SLEEP_ENTER (8.0) sits in SLEEP ONSET."""
    if norm < 2.0:
        return {
            "name": "WELL RESTED",
            "color": "success",
            "implication": "No sleep need — fully recovered",
        }
    if norm < 4.0:
        return {
            "name": "ALERT",
            "color": "success",
            "implication": "Normal wakefulness — no heavy pull",
        }
    if norm < 6.0:
        return {
            "name": "BUILDING",
            "color": "neutral",
            "implication": "Mild fatigue — been up a while",
        }
    if norm < 7.5:
        return {
            "name": "TIRED",
            "color": "warning",
            "implication": "Noticeably tired — cognition dipping",
        }
    # SLEEP_ENTER_ADENOSINE (8.0) sits in SLEEP ONSET, not mid-ALERT.
    if norm < max(8.5, SLEEP_ENTER_ADENOSINE + 0.5):
        return {
            "name": "SLEEP ONSET",
            "color": "error",
            "implication": "Near auto-sleep threshold — body pulling hard",
        }
    return {
        "name": "EXHAUSTED",
        "color": "error",
        "implication": "Past forced-sleep territory — monoamines under pressure",
    }


def _melatonin(norm: float) -> LabelResult:
    # Resting day ~0.2/10; night peak with offset can reach ~3–4/10 of max 250
    if norm < 0.5:
        return {
            "name": "DAYTIME",
            "color": "success",
            "implication": "Circadian sleep signal low — alertness available",
        }
    if norm < 1.5:
        return {
            "name": "EARLY EVENING",
            "color": "info",
            "implication": "Trace melatonin — day winding down",
        }
    if norm < 3.0:
        return {
            "name": "WINDING DOWN",
            "color": "info",
            "implication": "Melatonin rising — natural time to slow",
        }
    if norm < 5.0:
        return {
            "name": "DROWSY",
            "color": "warning",
            "implication": "Strong sleep signal — concentration costs more",
        }
    if norm < 7.0:
        return {
            "name": "SLEEP ONSET",
            "color": "warning",
            "implication": "Near peak melatonin — sleep imminent",
        }
    return {
        "name": "PEAK",
        "color": "error",
        "implication": "Melatonin at working maximum — deep night territory",
    }


def _cortisol(gap: float, norm: float) -> LabelResult:
    # Gap is vs circadian target — on-clock trough/peak is not crisis
    if gap <= -2.5:
        return {
            "name": "LOW",
            "color": "warning",
            "implication": "Below her stress floor for this hour",
        }
    if abs(gap) < 1.5:
        return {
            "name": "NORMAL",
            "color": "success",
            "implication": "On her circadian/allostatic track — grounded",
        }
    if gap < 3.0:
        return {
            "name": "ELEVATED",
            "color": "warning",
            "implication": "Above her track — edge, scanning",
        }
    if gap < 5.0:
        return {
            "name": "HIGH STRESS",
            "color": "error",
            "implication": "Sustained HPA elevation — defensive",
        }
    if norm >= 8.0 or gap >= 5.0:
        return {
            "name": "ACUTE STRESS",
            "color": "error",
            "implication": "High cortisol load — tunnel vision territory",
        }
    return {
        "name": "FLOODED",
        "color": "error",
        "implication": "Overwhelmed stress chemistry",
    }


def _generic(gap: float, norm: float) -> LabelResult:
    if norm < 0.3:
        return {
            "name": "FLOOR",
            "color": "neutral",
            "implication": "Near working floor",
        }
    if gap <= -2.0:
        return {
            "name": "LOW",
            "color": "warning",
            "implication": "Below her adapted baseline",
        }
    if abs(gap) < 1.5:
        return {
            "name": "BASELINE",
            "color": "success",
            "implication": "Near her adapted baseline",
        }
    if gap < 3.0:
        return {
            "name": "ELEVATED",
            "color": "info",
            "implication": "Above baseline",
        }
    if gap < 5.0:
        return {
            "name": "HIGH",
            "color": "warning",
            "implication": "Well above baseline",
        }
    return {
        "name": "PEAK",
        "color": "warning",
        "implication": "Near working ceiling",
    }


def label_for(
    name: str,
    value_nM: float,
    setpoint_nM: float,
    norm_max: float | None = None,
    hour: float | None = None,
) -> LabelResult:
    """
    Compute display label for one chemical.

    value_nM: tonic + phasic (or raw working units)
    setpoint_nM: live allostatic setpoint
    """
    p = CHEMICAL_PARAMS.get(name)
    if norm_max is None:
        norm_max = float(p["normalization_max"]) if p else 1.0
    else:
        norm_max = float(norm_max)

    target = _target_nM(name, setpoint_nM, hour)
    norm = _norm10(value_nM, norm_max)
    gap = norm - _norm10(max(0.0, target), norm_max)

    if name in TONE:
        return _tone(name, gap, norm)
    if name in SURGE:
        return _surge(name, gap, norm)
    if name in SLEEP:
        return _sleep_pressure(norm)
    if name in CLOCK_ABSOLUTE:
        return _melatonin(norm)
    if name in CLOCK_GAP:
        return _cortisol(gap, norm)
    return _generic(gap, norm)


def annotate_chemical(
    name: str,
    tonic: float,
    phasic: float,
    setpoint: float,
    hour: float | None = None,
) -> dict:
    """Full state DTO fields for one chemical (SPEC-63 API shape)."""
    p = CHEMICAL_PARAMS.get(name)
    if not p:
        return {
            "value": round(tonic + phasic, 3),
            "unit": "nM",
            "label": name,
            "normalized": 0.0,
            "normalized_10": 0.0,
            "setpoint": round(setpoint, 3),
            "setpoint_10": 0.0,
            "gap": 0.0,
            "label_color": "neutral",
            "implication": "",
        }

    combined = tonic + phasic
    norm_max = float(p["normalization_max"])
    target = _target_nM(name, setpoint, hour)
    n10 = _norm10(combined, norm_max)
    s10 = _norm10(setpoint, norm_max)  # allostatic only (decoder meaning)
    t10 = _norm10(max(0.0, target), norm_max)
    gap = n10 - t10
    lab = label_for(name, combined, setpoint, norm_max, hour)

    return {
        "value": round(combined, 3),
        "unit": display_unit(name),
        "label": lab["name"],
        "label_color": lab["color"],
        "implication": lab["implication"],
        # 0–1 fraction of max (legacy field used by theme hints)
        "normalized": round(combined / norm_max, 4) if norm_max else 0.0,
        "normalized_10": round(n10, 3),
        "setpoint": round(setpoint, 3),
        "setpoint_10": round(s10, 3),
        "gap": round(gap, 3),
        "norm_max": norm_max,
    }
