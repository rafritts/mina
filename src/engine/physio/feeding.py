"""
Feeding system — eat and drink tool handlers (SPEC-59).

LLM classifies food/drink properties; deltas are applied deterministically
from lookup tables so the math is in code, not in the model's output.
"""
from __future__ import annotations

import json
import re

from src.application.infra.client import chat_create, ENCODER_MODEL as MODEL
from src.application.infra import token_stats
from src.application.infra.log import log
from src.engine.bio.state import BiologicalState
from src.engine.chem.units import clamp_chemical

# ---------------------------------------------------------------------------
# Eat — classification tables
# ---------------------------------------------------------------------------

_MEAL_GLUCOSE: dict[str, dict[str, float]] = {
    "snack":    {"low": 10, "medium": 13, "high": 17, "very_high": 20},
    "light":    {"low": 20, "medium": 25, "high": 30, "very_high": 35},
    "moderate": {"low": 35, "medium": 40, "high": 47, "very_high": 50},
    "full":     {"low": 50, "medium": 55, "high": 62, "very_high": 65},
    "large":    {"low": 65, "medium": 70, "high": 77, "very_high": 80},
}

_MEAL_GHRELIN: dict[str, float] = {
    "snack":    -125.0,
    "light":    -175.0,
    "moderate": -250.0,
    "full":     -350.0,
    "large":    -425.0,
}

_MEAL_LEPTIN: dict[str, float] = {
    "snack":    0.5,
    "light":    0.8,
    "moderate": 1.2,
    "full":     1.6,
    "large":    2.0,
}

_GI_INSULIN: dict[str, float] = {
    "low":       8.0,
    "medium":   14.0,
    "high":     28.0,
    "very_high": 42.0,
}

_EAT_CLASSIFY_SYSTEM = """\
You are classifying a meal for a biological simulation. Given a food description, \
output a JSON object with these exact fields. No prose, no markdown, no fences.

"meal_size"      — one of: snack, light, moderate, full, large
                   snack = a handful of something; light = soup or salad; moderate = typical meal;
                   full = satisfying complete meal; large = big or multi-course
"glycemic_index" — one of: low, medium, high, very_high
                   low = meat/fish/eggs/nuts; medium = whole grains, legumes; high = white bread/pasta/rice;
                   very_high = candy, juice, pastries, sugary cereal
"protein_rich"   — true if primary protein source (meat, fish, eggs, legumes, dairy), else false
"comfort_food"   — true if this would typically feel emotionally comforting (pasta, bread, soup,
                   sweets, rice dishes, cheese, chocolate), else false
"water_rich"     — true if notably high water content (soup, broth, fruit, smoothie), else false
"enjoyed"        — true unless description clearly implies distaste or forced eating
"summary"        — brief natural phrase of what was eaten, for tool result text"""


def _classify_food(description: str) -> dict | None:
    messages = [
        {"role": "system", "content": _EAT_CLASSIFY_SYSTEM},
        {"role": "user", "content": description},
    ]
    try:
        response = chat_create(model=MODEL, messages=messages, temperature=0.2, max_tokens=256)
        token_stats.record_response("eat_classify", response)
        raw = (response.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE).strip()
        return json.loads(raw)
    except Exception as e:
        log("FEEDING/EAT_CLASSIFY/ERR", str(e))
        return None


def handle_eat(args: dict, state: BiologicalState) -> tuple[str, BiologicalState]:
    description = args.get("description", "something").strip()

    classified = _classify_food(description)
    if not classified:
        classified = {
            "meal_size": "moderate", "glycemic_index": "medium",
            "protein_rich": False, "comfort_food": False,
            "water_rich": False, "enjoyed": True,
            "summary": description,
        }

    meal_size   = classified.get("meal_size", "moderate")
    gi          = classified.get("glycemic_index", "medium")
    protein     = bool(classified.get("protein_rich", False))
    comfort     = bool(classified.get("comfort_food", False))
    water_rich  = bool(classified.get("water_rich", False))
    enjoyed     = bool(classified.get("enjoyed", True))
    summary     = classified.get("summary", description)

    if meal_size not in _MEAL_GLUCOSE:
        meal_size = "moderate"
    if gi not in _GI_INSULIN:
        gi = "medium"

    ghrelin_before = state.neuroendocrine.get("ghrelin", 400.0)
    glucose_before = state.chemicals.get("glucose", 85.0)

    # ── Glucose ──────────────────────────────────────────────────────────────
    glucose_delta = _MEAL_GLUCOSE[meal_size][gi]
    if glucose_before < 55.0:
        glucose_delta += 10.0

    # ── Ghrelin suppression ──────────────────────────────────────────────────
    ghrelin_delta = _MEAL_GHRELIN[meal_size]
    new_ghrelin = max(50.0, ghrelin_before + ghrelin_delta)
    state.neuroendocrine["ghrelin"] = new_ghrelin

    # ── Leptin boost ─────────────────────────────────────────────────────────
    leptin_now = state.neuroendocrine.get("leptin", 15.0)
    state.neuroendocrine["leptin"] = max(2.0, min(40.0, leptin_now + _MEAL_LEPTIN[meal_size]))

    # ── Insulin spike ────────────────────────────────────────────────────────
    insulin_now = state.neuroendocrine.get("insulin", 5.0)
    state.neuroendocrine["insulin"] = max(0.0, insulin_now + _GI_INSULIN[gi])

    # ── First-order chemicals via standard delta dict ─────────────────────────
    deltas: dict[str, float] = {}

    deltas["glucose"] = glucose_delta

    # Serotonin
    if protein or comfort:
        deltas["serotonin"] = 4.0
    else:
        deltas["serotonin"] = 2.0

    # Endorphins
    if comfort and enjoyed:
        deltas["endorphins"] = 7.0
    elif enjoyed:
        deltas["endorphins"] = 2.0
    else:
        deltas["endorphins"] = 1.0

    # Cortisol relief from hunger satisfied
    if ghrelin_before > 500.0:
        deltas["cortisol"] = -12.0
    elif ghrelin_before > 300.0:
        deltas["cortisol"] = -7.0

    # Dopamine from enjoyed food
    if enjoyed:
        deltas["dopamine"] = 5.0

    # Hydration from water-rich foods
    if water_rich:
        deltas["hydration"] = 0.6

    # Apply to state
    for chem, delta in deltas.items():
        current = state.chemicals.get(chem, 0.0)
        state.chemicals[chem] = clamp_chemical(chem, current + delta)

    delta_str = ", ".join(f"{k}: {v:+.1f}" for k, v in deltas.items())
    log("FEEDING/EAT", f"{meal_size}/{gi} comfort={comfort} protein={protein} | {delta_str}")

    return f"You eat {summary}.", state


# ---------------------------------------------------------------------------
# Drink — classification tables
# ---------------------------------------------------------------------------

_VOLUME_MULT: dict[str, float] = {
    "sip":    0.25,
    "small":  0.5,
    "medium": 1.0,
    "large":  1.5,
    "bottle": 2.5,
}

_VOLUME_ML: dict[str, float] = {
    "sip":    30.0,
    "small":  120.0,
    "medium": 240.0,
    "large":  480.0,
    "bottle": 720.0,
}

# Base effects at medium (1.0) volume — all values are scaled by _VOLUME_MULT
_DRINK_BASE: dict[str, dict[str, float]] = {
    "water":   {"hydration": 2.0},
    "milk":    {"hydration": 1.6, "glucose": 10.0, "serotonin": 1.5, "endorphins": 3.5},
    "juice":   {"hydration": 1.3, "glucose": 18.0},
    "tea":     {"hydration": 1.3, "gaba": 0.2},
    "coffee":  {"hydration": 0.6, "acetylcholine": 3.5, "cortisol": 22.0,
                "norepinephrine": 15.0, "sleep_pressure": -10.0},
    "soup":    {"hydration": 1.5, "glucose": 8.0, "serotonin": 2.0, "endorphins": 4.0},
    "alcohol": {"hydration": 0.45, "gaba": 0.55},
    "soda":    {"hydration": 0.85, "glucose": 22.0},
    "other":   {"hydration": 1.0},
}

# Ghrelin suppression from drinking — small distension signal
_DRINK_GHRELIN: dict[str, float] = {
    "water":   -30.0,
    "milk":    -60.0,
    "juice":   -60.0,
    "tea":     -25.0,
    "coffee":  -20.0,
    "soup":    -70.0,
    "alcohol": -40.0,
    "soda":    -55.0,
    "other":   -25.0,
}

_DRINK_CLASSIFY_SYSTEM = """\
You are classifying a drink for a biological simulation. Given a drink description, \
output a JSON object with these exact fields. No prose, no markdown, no fences.

"drink_type"    — one of: water, milk, juice, tea, coffee, soup, alcohol, soda, other
"volume"        — one of: sip, small, medium, large, bottle
                  sip=<2oz, small=4-8oz, medium=8-12oz, large=12-20oz, bottle=20oz+
"caffeinated"   — true for coffee, black/green tea, cola, energy drinks; false otherwise
"abv_estimate"  — float: 0.0 for non-alcoholic; e.g. 0.05 for beer, 0.12 for wine, 0.40 for spirits
"summary"       — brief natural phrase of what was drunk, for tool result text"""


def _classify_drink(description: str) -> dict | None:
    messages = [
        {"role": "system", "content": _DRINK_CLASSIFY_SYSTEM},
        {"role": "user", "content": description},
    ]
    try:
        response = chat_create(model=MODEL, messages=messages, temperature=0.2, max_tokens=128)
        token_stats.record_response("drink_classify", response)
        raw = (response.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE).strip()
        return json.loads(raw)
    except Exception as e:
        log("FEEDING/DRINK_CLASSIFY/ERR", str(e))
        return None


def handle_drink(args: dict, state: BiologicalState) -> tuple[str, BiologicalState]:
    description = args.get("description", "something").strip()

    classified = _classify_drink(description)
    if not classified:
        classified = {
            "drink_type": "water", "volume": "medium",
            "caffeinated": False, "abv_estimate": 0.0,
            "summary": description,
        }

    drink_type  = classified.get("drink_type", "other")
    volume      = classified.get("volume", "medium")
    caffeinated = bool(classified.get("caffeinated", False))
    abv         = float(classified.get("abv_estimate", 0.0))
    summary     = classified.get("summary", description)

    if drink_type not in _DRINK_BASE:
        drink_type = "other"
    if volume not in _VOLUME_MULT:
        volume = "medium"

    mult = _VOLUME_MULT[volume]

    # ── Build scaled delta dict ───────────────────────────────────────────────
    deltas: dict[str, float] = {}
    for chem, base in _DRINK_BASE[drink_type].items():
        deltas[chem] = round(base * mult, 3)

    # Caffeinated soda: partial coffee-like stimulant effect
    if drink_type == "soda" and caffeinated:
        deltas["cortisol"]       = round(deltas.get("cortisol", 0.0)       + 13.0 * mult, 3)
        deltas["norepinephrine"] = round(deltas.get("norepinephrine", 0.0) + 9.0  * mult, 3)
        deltas["sleep_pressure"] = round(deltas.get("sleep_pressure", 0.0) - 5.0  * mult, 3)

    # Alcohol: BAC delta via Widmark formula (assume 60kg body weight, r=0.55 for women)
    if drink_type == "alcohol" and abv > 0.0:
        volume_ml = _VOLUME_ML[volume]
        alcohol_g = volume_ml * 0.789 * abv
        bac_delta = alcohol_g / (60_000.0 * 0.55)  # g/dL
        deltas["bac"] = round(bac_delta, 4)

    # ── Ghrelin suppression ───────────────────────────────────────────────────
    ghrelin_now = state.neuroendocrine.get("ghrelin", 400.0)
    ghrelin_delta = _DRINK_GHRELIN.get(drink_type, -25.0) * mult
    state.neuroendocrine["ghrelin"] = max(50.0, ghrelin_now + ghrelin_delta)

    # ── Apply first-order deltas ──────────────────────────────────────────────
    for chem, delta in deltas.items():
        current = state.chemicals.get(chem, 0.0)
        state.chemicals[chem] = clamp_chemical(chem, current + delta)

    delta_str = ", ".join(f"{k}: {v:+.3f}" for k, v in deltas.items())
    log("FEEDING/DRINK", f"{drink_type}/{volume} caff={caffeinated} abv={abv:.2f} | {delta_str}")

    return f"You drink {summary}.", state
