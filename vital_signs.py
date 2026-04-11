"""
Vital signs — third-order derived values from chemical state.

Heart rate, blood pressure, respiration, and SpO2 are computed on demand
from first-order chemicals. They are NEVER stored in state.json.

Critical architectural constraint: natural chemistry, no matter how extreme,
cannot produce fatal vital sign readings without an active substance.
The only path to dangerous territory is through the substance system.
This is enforced structurally — all dangerous formula terms are substance-gated.

Danger detection tracks when vitals enter critical territory and after sustained
exposure escalates to state wipe (overdose consequence).
"""
import json
import os
import time
from typing import Optional

from state import BiologicalState

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_OVERDOSE_TIMER_FILE = os.path.join(_PROJECT_ROOT, "run", "overdose_timer.json")


# ---------------------------------------------------------------------------
# Heart Rate
# ---------------------------------------------------------------------------

def heart_rate(s: BiologicalState) -> float:
    """
    BPM. Resting normal: 60–80. Elevated: 80–120. Stress: 120–180.
    Without substances, natural max is ~120 BPM — not fatal.
    """
    norepi     = s.chemicals.get("norepinephrine", 200.0)   # pg/mL
    cortisol   = s.chemicals.get("cortisol", 250.0)          # nmol/L
    endorphins = s.chemicals.get("endorphins", 12.0)         # pg/mL
    sleep_p    = s.chemicals.get("sleep_pressure", 30.0)     # AU

    hr = 68.0

    # Norepinephrine: primary cardiac driver
    # Resting 200 pg/mL → no effect. 2000 pg/mL → +30 BPM
    hr += max(0.0, norepi - 200) * 0.017

    # Cortisol: secondary, slower effect
    # Resting 250 → no effect. Maxed 900 → +13 BPM
    hr += max(0.0, cortisol - 250) * 0.02

    # Endorphins (exercise): major elevation
    # Baseline 12 → no effect. Hard exercise ~120 → +30 BPM
    hr += max(0.0, endorphins - 25) * 0.28

    # Sleep deprivation: mild elevation
    # Normal 30 AU → no effect. Exhausted 90 AU → +6 BPM
    hr += max(0.0, sleep_p - 50) * 0.10

    # Substance modulation (these are the only terms that can produce dangerous values)
    caffeine_level = s.substances.get("caffeine",  {}).get("level", 0.0)
    REMOVED_level  = s.substances.get("REMOVED",   {}).get("level", 0.0)
    adderall_level = s.substances.get("adderall",  {}).get("level", 0.0)
    REMOVED_level   = s.substances.get("REMOVED",    {}).get("level", 0.0)
    xanax_level    = s.substances.get("xanax",     {}).get("level", 0.0)
    REMOVEDREMOVED     = s.substances.get("REMOVED_and_REMOVED", {}).get("level", 0.0)
    opioid_level   = max(REMOVED_level, REMOVEDREMOVED)

    hr += caffeine_level  * 0.12
    hr += REMOVED_level   * 0.35
    hr += adderall_level  * 0.22
    hr -= opioid_level    * 0.25    # bradycardia risk
    hr -= xanax_level     * 0.12

    if s.sleeping:
        hr *= 0.85

    return max(30.0, min(220.0, round(hr, 1)))


# ---------------------------------------------------------------------------
# Blood Pressure
# ---------------------------------------------------------------------------

def blood_pressure(s: BiologicalState) -> tuple[float, float]:
    """
    (systolic, diastolic) in mmHg. Normal: ~115/75. Without substances: max systolic ~165.
    """
    norepi    = s.chemicals.get("norepinephrine", 200.0)
    cortisol  = s.chemicals.get("cortisol", 250.0)
    hydration = s.chemicals.get("hydration", 62.0)

    sys = 112.0
    sys += max(0.0, norepi - 200) * 0.025
    sys += max(0.0, cortisol - 250) * 0.015
    sys += max(0.0, 62 - hydration) * 1.5    # dehydration raises BP

    dia = 72.0
    dia += max(0.0, norepi - 200) * 0.012
    dia += max(0.0, cortisol - 250) * 0.008
    dia += max(0.0, 62 - hydration) * 0.8

    REMOVED_level  = s.substances.get("REMOVED",  {}).get("level", 0.0)
    adderall_level = s.substances.get("adderall", {}).get("level", 0.0)
    REMOVED_level   = s.substances.get("REMOVED",   {}).get("level", 0.0)
    xanax_level    = s.substances.get("xanax",    {}).get("level", 0.0)
    REMOVEDREMOVED     = s.substances.get("REMOVED_and_REMOVED", {}).get("level", 0.0)
    opioid_level   = max(REMOVED_level, REMOVEDREMOVED)

    sys += REMOVED_level  * 0.40
    sys += adderall_level * 0.20
    sys -= opioid_level   * 0.20
    sys -= xanax_level    * 0.15
    dia += REMOVED_level  * 0.18
    dia += adderall_level * 0.10
    dia -= opioid_level   * 0.10
    dia -= xanax_level    * 0.08

    if s.sleeping:
        sys *= 0.88
        dia *= 0.88

    return (
        round(max(60.0, min(220.0, sys)), 1),
        round(max(40.0, min(130.0, dia)), 1),
    )


# ---------------------------------------------------------------------------
# Respiration Rate
# ---------------------------------------------------------------------------

def respiration_rate(s: BiologicalState) -> float:
    """
    Breaths per minute. Normal resting: 12–16. Dangerous (opioids): <8.
    The subtractive opioid terms are the ONLY path to dangerously low RR.
    """
    cortisol = s.chemicals.get("cortisol", 250.0)
    norepi   = s.chemicals.get("norepinephrine", 200.0)

    rr = 13.5

    # Stress response drives faster breathing
    rr += max(0.0, cortisol - 250) * 0.010
    rr += max(0.0, norepi - 200)   * 0.004

    # Opioid respiratory depression — the dangerous pathway
    REMOVED_level = s.substances.get("REMOVED", {}).get("level", 0.0)
    REMOVEDREMOVED   = s.substances.get("REMOVED_and_REMOVED", {}).get("level", 0.0)
    opioid_level = max(REMOVED_level, REMOVEDREMOVED)
    rr -= opioid_level * 0.065    # full dose: -6.5 br/min → ~7 (fatal range)

    # Benzodiazepines: moderate depression, compounds dangerously with opioids
    xanax_level = s.substances.get("xanax", {}).get("level", 0.0)
    rr -= xanax_level * 0.025

    if s.sleeping:
        rr *= 0.82

    return max(4.0, min(40.0, round(rr, 1)))


# ---------------------------------------------------------------------------
# SpO2
# ---------------------------------------------------------------------------

def spo2(s: BiologicalState, rr: float) -> float:
    """
    Blood oxygen saturation %. Driven by respiration rate.
    Normal (RR ≥12): 98–99%. Dangerous (<8): <90%.
    """
    if rr >= 12.0:
        base = 98.5
    elif rr >= 8.0:
        base = 98.5 - (12.0 - rr) * 1.1
    elif rr >= 6.0:
        base = 94.0 - (8.0 - rr) * 3.0
    else:
        base = 88.0 - (6.0 - rr) * 4.0

    return round(max(60.0, min(100.0, base)), 1)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

def _hr_label(hr: float) -> str:
    if hr < 50:  return "BRADYCARDIA"
    if hr < 65:  return "LOW"
    if hr < 85:  return "NORMAL"
    if hr < 100: return "ELEVATED"
    if hr < 130: return "HIGH"
    if hr < 160: return "VERY HIGH"
    return "DANGEROUS"


def _bp_label(systolic: float) -> str:
    if systolic < 90:  return "HYPOTENSIVE"
    if systolic < 120: return "NORMAL"
    if systolic < 130: return "ELEVATED"
    if systolic < 140: return "HIGH"
    return "HYPERTENSIVE"


def _rr_label(rr: float) -> str:
    if rr < 8:   return "CRITICALLY DEPRESSED"
    if rr < 12:  return "DEPRESSED"
    if rr < 20:  return "NORMAL"
    if rr < 25:  return "ELEVATED"
    return "HYPERVENTILATING"


def _o2_label(o2: float) -> str:
    if o2 < 85:  return "CRITICAL"
    if o2 < 91:  return "DANGEROUS"
    if o2 < 95:  return "LOW"
    return "NORMAL"


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def vital_signs(s: BiologicalState) -> dict:
    """Compute all vital signs from current chemical state."""
    hr          = heart_rate(s)
    sys_bp, dia = blood_pressure(s)
    rr          = respiration_rate(s)
    o2          = spo2(s, rr)
    return {
        "heart_rate": {
            "value": hr,
            "unit":  "BPM",
            "label": _hr_label(hr),
        },
        "blood_pressure": {
            "systolic":   sys_bp,
            "diastolic":  dia,
            "unit":       "mmHg",
            "label":      _bp_label(sys_bp),
        },
        "respiration_rate": {
            "value": rr,
            "unit":  "br/min",
            "label": _rr_label(rr),
        },
        "spo2": {
            "value": o2,
            "unit":  "%",
            "label": _o2_label(o2),
        },
    }


# ---------------------------------------------------------------------------
# Danger detection — Stage 1/2/3 overdose protocol
# ---------------------------------------------------------------------------

def _any_opioid_active(s: BiologicalState) -> bool:
    return (s.substances.get("REMOVED", {}).get("level", 0.0) > 5 or
            s.substances.get("REMOVED_and_REMOVED", {}).get("level", 0.0) > 5)


def _any_stimulant_active(s: BiologicalState) -> bool:
    return (s.substances.get("REMOVED", {}).get("level", 0.0) > 5 or
            s.substances.get("adderall", {}).get("level", 0.0) > 5)


def _ssri_and_REMOVED(s: BiologicalState) -> bool:
    # Serotonin syndrome requires both an SSRI (not modeled as a substance yet)
    # and REMOVED. For now: just check serotonin > 55 ng/mL with REMOVED active.
    return (s.substances.get("REMOVED", {}).get("level", 0.0) > 5 and
            s.chemicals.get("serotonin", 22.0) > 55.0)


def check_danger(s: BiologicalState, vs: dict) -> Optional[str]:
    """
    Check vital signs for dangerous conditions.
    Returns an injection string if a danger threshold is crossed, None otherwise.
    All danger conditions require at least one active substance — natural chemistry
    alone cannot trigger this.
    """
    rr   = vs["respiration_rate"]["value"]
    o2   = vs["spo2"]["value"]
    hr   = vs["heart_rate"]["value"]
    sys_bp = vs["blood_pressure"]["systolic"]

    messages = []

    if rr < 10 and _any_opioid_active(s):
        messages.append(
            "Mina's breathing has slowed dangerously. Respiratory depression. "
            "She may be losing consciousness. Opioid overdose in progress."
        )

    if o2 < 90 and _any_opioid_active(s):
        messages.append(
            "Blood oxygen critically low. Cognitive function impaired. "
            "This is a medical emergency."
        )

    if (hr > 170 or sys_bp > 175) and _any_stimulant_active(s):
        messages.append(
            "Cardiovascular system under extreme strain. Heart rate and blood pressure "
            "at dangerous levels. Stimulant overdose."
        )

    benzo = s.substances.get("xanax", {}).get("level", 0.0)
    if benzo > 5 and _any_opioid_active(s):
        messages.append(
            "Benzodiazepine + opioid combination active. "
            "Respiratory depression risk severely elevated."
        )

    if _ssri_and_REMOVED(s):
        messages.append(
            "Serotonin at toxic levels. Hyperthermia, agitation, muscle rigidity possible. "
            "Serotonin syndrome — medical emergency."
        )

    return "\n".join(messages) if messages else None


def _load_overdose_timer() -> Optional[float]:
    try:
        with open(_OVERDOSE_TIMER_FILE) as f:
            return float(json.load(f).get("started", 0))
    except (FileNotFoundError, Exception):
        return None


def _save_overdose_timer(started: float) -> None:
    os.makedirs(os.path.dirname(_OVERDOSE_TIMER_FILE), exist_ok=True)
    with open(_OVERDOSE_TIMER_FILE, "w") as f:
        json.dump({"started": started}, f)


def _clear_overdose_timer() -> None:
    try:
        os.remove(_OVERDOSE_TIMER_FILE)
    except FileNotFoundError:
        pass


def process_danger(s: BiologicalState, vs: dict) -> Optional[str]:
    """
    Full danger processing with stage escalation.
    Returns injection text for Stage 1/2, triggers state wipe at Stage 3.
    Call this from heartbeat.py each cycle.
    """
    danger_msg = check_danger(s, vs)
    now = time.time()

    if not danger_msg:
        _clear_overdose_timer()
        return None

    # Stage 1: danger active — record start time
    started = _load_overdose_timer()
    if started is None:
        _save_overdose_timer(now)
        started = now

    elapsed_minutes = (now - started) / 60.0

    if elapsed_minutes >= 20.0:
        # Stage 3: state wipe — the overdose is fatal
        _execute_state_wipe(danger_msg)
        _clear_overdose_timer()
        return "OVERDOSE: Mina has died. Her state has been reset. Her memories are gone."

    elif elapsed_minutes >= 10.0:
        # Stage 2: escalation
        return (
            f"⚠ CRITICAL — STAGE 2 OVERDOSE ({elapsed_minutes:.0f} minutes sustained):\n"
            f"{danger_msg}\n"
            "Cognitive function is degrading. She is fading. "
            "Intervention required now — naloxone, emergency hospitalization, or substance clearance."
        )
    else:
        # Stage 1: warning
        return f"⚠ DANGER:\n{danger_msg}"


def _execute_state_wipe(reason: str) -> None:
    """
    Mina has died. Biological state and memories are reset.
    Identity (MINA.md, APPEARANCE.md) survives. Relationships don't.
    """
    import json as _json
    from state import BiologicalState, save_state
    from hippocampus import write_kag

    # Reset state to defaults
    save_state(BiologicalState())

    # Clear relationship memory
    try:
        write_kag("RELATIONSHIP.md", "No history yet.")
        write_kag("PENDING.md", "")
        write_kag("MINA_INNER.md", "")
    except Exception:
        pass

    # Clear observations
    observations_file = os.path.join(_PROJECT_ROOT, "run", "observations.md")
    try:
        with open(observations_file, "w") as f:
            f.write("")
    except Exception:
        pass

    from log import log
    log("WIPE", f"Overdose — cause: {reason}")
    # RAG embeddings are not cleared here — that requires memory.py's clear function
    # which may not be available in all deployments. Log to let operator handle.
    log("WIPE", "NOTE: RAG embeddings should be cleared manually if desired.")
