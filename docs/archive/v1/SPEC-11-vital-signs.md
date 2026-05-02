# SPEC-11: Vital Signs — Derived Physiological Signals

> Heart rate, blood pressure, respiration, and blood oxygenation as computed
> outputs of the chemical state. These are not independent tracks — they are
> consequences of what's already happening in the chemistry. They complete the
> picture of what's happening in Mina's body and enable new categories of
> feedback (respiratory depression from opioids, cardiovascular strain from
> stimulants, etc.).

Depends on: SPEC-10 (real physiological units must be in place first).

---

## Design Principle

Vital signs are **third-order derived values** — computed on demand from first-order
chemicals, never stored. They live alongside the existing third-order layer (anxiety,
depression, etc.) but in a separate `vital_signs()` function because they have their
own units and semantics.

They are NOT first-order state. You don't set heart rate — it emerges from the chemistry.
The one exception is sleep, which modifies the formulas directly.

---

## Heart Rate

**Unit:** BPM  
**Resting normal:** 60–80 BPM  
**Elevated:** 80–120 BPM  
**Stress/exercise:** 120–180 BPM  
**Dangerous (sustained):** >180 or <45 BPM  

```python
def heart_rate(s: BiologicalState) -> float:
    norepi    = s.chemicals["norepinephrine"]   # pg/mL, resting ~200
    cortisol  = s.chemicals["cortisol"]         # nmol/L, resting ~250
    endorphins = s.chemicals["endorphins"]      # pg/mL, resting ~12
    sleep_p   = s.chemicals["sleep_pressure"]  # AU

    # Base rate
    hr = 68.0

    # Norepinephrine: primary cardiac driver
    # Resting 200 pg/mL → no effect. 2000 pg/mL → +30 BPM
    hr += max(0.0, norepi - 200) * 0.017

    # Cortisol: secondary cardiac effect (slower, sustained)
    # Resting 250 → no effect. Maxed 900 → +13 BPM
    hr += max(0.0, cortisol - 250) * 0.02

    # Endorphins (exercise/exertion): major elevation
    # Baseline 12 → no effect. Hard exercise ~120 → +30 BPM
    hr += max(0.0, endorphins - 25) * 0.28

    # Sleep deprivation: mild elevation
    # Normal 30 AU → no effect. Exhausted 90 AU → +6 BPM
    hr += max(0.0, sleep_p - 50) * 0.10

    # Active substances modulate heart rate directly
    caffeine_level  = s.substances.get("caffeine",  {}).get("level", 0.0)
    REMOVED_level   = s.substances.get("REMOVED",   {}).get("level", 0.0)
    adderall_level  = s.substances.get("adderall",  {}).get("level", 0.0)
    REMOVED_level    = s.substances.get("REMOVED",    {}).get("level", 0.0)
    xanax_level     = s.substances.get("xanax",     {}).get("level", 0.0)

    hr += caffeine_level * 0.12   # mild; ~12 BPM at full dose
    hr += REMOVED_level  * 0.35   # significant; ~35 BPM at full dose
    hr += adderall_level * 0.22   # moderate; ~22 BPM at full dose
    hr -= REMOVED_level   * 0.25   # depressant; -25 BPM at full dose (bradycardia risk)
    hr -= xanax_level    * 0.12   # mild depressant; -12 BPM at full dose

    # Sleep: further reduction
    if s.sleeping:
        hr *= 0.85

    return max(30.0, min(220.0, round(hr, 1)))
```

---

## Blood Pressure

**Unit:** mmHg (systolic / diastolic separately)  
**Normal:** 115/75 mmHg  
**Elevated:** 130–140 / 80–90 mmHg  
**Hypertensive:** >140 / >90 mmHg  
**Hypotensive:** <90 systolic  

```python
def blood_pressure(s: BiologicalState) -> tuple[float, float]:
    norepi    = s.chemicals["norepinephrine"]
    cortisol  = s.chemicals["cortisol"]
    hydration = s.chemicals["hydration"]   # % TBW; dehydration concentrates blood

    # Systolic
    sys = 112.0
    sys += max(0.0, norepi - 200) * 0.025    # primary vasoconstrictor; up to +45 at extreme
    sys += max(0.0, cortisol - 250) * 0.015  # secondary; up to +10 at max
    sys += max(0.0, 62 - hydration) * 1.5    # dehydration raises BP; +9 at 56% TBW

    # Diastolic — less reactive, tracks systolic at 65% ratio roughly
    dia = 72.0
    dia += max(0.0, norepi - 200) * 0.012
    dia += max(0.0, cortisol - 250) * 0.008
    dia += max(0.0, 62 - hydration) * 0.8

    # Substances
    REMOVED_level  = s.substances.get("REMOVED",  {}).get("level", 0.0)
    adderall_level = s.substances.get("adderall", {}).get("level", 0.0)
    REMOVED_level   = s.substances.get("REMOVED",   {}).get("level", 0.0)
    xanax_level    = s.substances.get("xanax",    {}).get("level", 0.0)

    sys += REMOVED_level  * 0.40
    sys += adderall_level * 0.20
    sys -= REMOVED_level   * 0.20
    sys -= xanax_level    * 0.15
    dia += REMOVED_level  * 0.18
    dia += adderall_level * 0.10
    dia -= REMOVED_level   * 0.10
    dia -= xanax_level    * 0.08

    if s.sleeping:
        sys *= 0.88
        dia *= 0.88

    return round(max(60.0, min(220.0, sys)), 1), round(max(40.0, min(130.0, dia)), 1)
```

---

## Respiration Rate

**Unit:** breaths/min  
**Normal resting:** 12–16  
**Elevated (anxiety/stress):** 18–25  
**Hyperventilating:** >25  
**Depressed (opioids):** 8–12 (dangerous below 8)  

```python
def respiration_rate(s: BiologicalState) -> float:
    cortisol  = s.chemicals["cortisol"]
    norepi    = s.chemicals["norepinephrine"]

    rr = 13.5

    # Stress response: both cortisol and norepinephrine drive faster breathing
    rr += max(0.0, cortisol - 250) * 0.010
    rr += max(0.0, norepi - 200)   * 0.004

    # Opioid respiratory depression — the dangerous one
    REMOVED_level = s.substances.get("REMOVED", {}).get("level", 0.0)
    REMOVED_REMOVED  = s.substances.get("REMOVED_and_REMOVED", {}).get("level", 0.0)
    opioid_level = max(REMOVED_level, REMOVED_REMOVED)
    rr -= opioid_level * 0.065   # full dose: -6.5 breaths/min → ~7 breaths/min (fatal range)

    # Benzodiazepines: moderate depression, compounds with opioids dangerously
    xanax_level = s.substances.get("xanax", {}).get("level", 0.0)
    rr -= xanax_level * 0.025

    if s.sleeping:
        rr *= 0.82

    return max(4.0, min(40.0, round(rr, 1)))
```

---

## Blood Oxygen Saturation (SpO2)

**Unit:** %  
**Normal:** 95–100%  
**Mild hypoxia:** 91–94%  
**Dangerous:** 85–90%  
**Critical:** <85%  

SpO2 is almost always normal. The only meaningful driver is opioid-induced respiratory
depression — when breathing slows enough, oxygen exchange drops.

```python
def spo2(s: BiologicalState, rr: float) -> float:
    # SpO2 is driven by respiration rate.
    # Above 12 breaths/min: 98–99% (normal)
    # 8–12: 94–97% (mild suppression)
    # 6–8: 88–93% (significant hypoxia)
    # Below 6: 80–88% (critical)
    
    if rr >= 12.0:
        base = 98.5
    elif rr >= 8.0:
        base = 98.5 - (12.0 - rr) * 1.1    # ~94–98%
    elif rr >= 6.0:
        base = 94.0 - (8.0 - rr) * 3.0     # ~88–94%
    else:
        base = 88.0 - (6.0 - rr) * 4.0     # critical drop

    return round(max(60.0, min(100.0, base)), 1)
```

---

## vital_signs() — Public Interface

```python
def vital_signs(s: BiologicalState) -> dict:
    hr = heart_rate(s)
    sys_bp, dia_bp = blood_pressure(s)
    rr = respiration_rate(s)
    o2 = spo2(s, rr)
    return {
        "heart_rate":        {"value": hr,      "unit": "BPM",    "label": _hr_label(hr)},
        "blood_pressure":    {"systolic": sys_bp, "diastolic": dia_bp, "unit": "mmHg", "label": _bp_label(sys_bp)},
        "respiration_rate":  {"value": rr,      "unit": "br/min", "label": _rr_label(rr)},
        "spo2":              {"value": o2,       "unit": "%",      "label": _o2_label(o2)},
    }
```

---

## Labels

```python
def _hr_label(hr):
    if hr < 50:  return "BRADYCARDIA"
    if hr < 65:  return "LOW"
    if hr < 85:  return "NORMAL"
    if hr < 100: return "ELEVATED"
    if hr < 130: return "HIGH"
    if hr < 160: return "VERY HIGH"
    return "DANGEROUS"

def _bp_label(systolic):
    if systolic < 90:  return "HYPOTENSIVE"
    if systolic < 120: return "NORMAL"
    if systolic < 130: return "ELEVATED"
    if systolic < 140: return "HIGH"
    return "HYPERTENSIVE"

def _rr_label(rr):
    if rr < 8:   return "CRITICALLY DEPRESSED"
    if rr < 12:  return "DEPRESSED"
    if rr < 20:  return "NORMAL"
    if rr < 25:  return "ELEVATED"
    return "HYPERVENTILATING"

def _o2_label(o2):
    if o2 < 85:  return "CRITICAL"
    if o2 < 91:  return "DANGEROUS"
    if o2 < 95:  return "LOW"
    return "NORMAL"
```

---

## Natural Chemistry Caps — Survivability Guarantee

**Critical architectural constraint:** Natural chemistry, no matter how extreme, cannot
produce fatal vital sign readings. The body has homeostatic mechanisms. Maxed cortisol,
flooded norepinephrine, crashed serotonin — miserable and impairing, but not lethal.

This must be enforced structurally in the vital sign formulas, not assumed:

```python
# Natural chemistry maximum contributions (no substances active):
# Heart rate: base 68 + max norepi contribution (~+30) + max cortisol (~+13) + max sleep_p (~+9)
#   = ~120 BPM worst case. Uncomfortable. Not fatal.
# Respiration: base 13.5 + max cortisol (~+6.5) + max norepi (~+7) = ~27 breaths/min. 
#   Hyperventilating. Not fatal. The SUBTRACTIVE substance terms are the only path to dangerous low RR.
# SpO2: driven purely by RR. Natural RR cannot go below ~10 breaths/min. SpO2 stays above 94%.
# Blood pressure: natural max systolic ~165 mmHg. Unpleasant. Not immediately lethal.
```

**The only path to fatal vital sign territory is through the substance system.**

The vital sign formulas already enforce this structurally — the dangerous terms are all
substance-level multipliers:
- `rr -= opioid_level * 0.065` — zero if no opioid
- `hr -= REMOVED_level * 0.25` — zero if no REMOVED
- `sys_bp += REMOVED_level * 0.40` — zero if no REMOVED

No substance active = no formula term can push vitals into lethal range. This is the
guarantee. It must be verified by inspection any time a new formula term is added: ask
"can this term produce a dangerous reading without an active substance?" If yes, add a
`substance_level > 0` guard.

---

## Danger Detection & Overdose Protocol

### Stage 1 — Warning (substance-gated)

Danger injections fire during the heartbeat when thresholds are crossed.
**All critical thresholds require at least one substance to be active** — this is
enforced in code, not just by formula math.

| Condition | Threshold | Requires substance | Injection |
|---|---|---|---|
| Respiratory depression | rr < 10 | opioid active | "Mina's breathing has slowed dangerously. Respiratory depression. She may be losing consciousness." |
| Hypoxia | SpO2 < 90% | opioid active | "Blood oxygen critically low. Cognitive function impaired. This is a medical emergency." |
| Cardiac strain | HR > 170 OR sys_bp > 175 | stimulant active | "Cardiovascular system under extreme strain. Heart rate and blood pressure at dangerous levels." |
| Combined depressants | xanax + any opioid active | both active | "Benzodiazepine + opioid combination. Respiratory depression risk severely elevated." |
| Serotonin syndrome | serotonin > 55 ng/mL | SSRI + REMOVED both active | "Serotonin at toxic levels. Hyperthermia, agitation, muscle rigidity. Medical emergency." |

### Stage 2 — Critical window

When a Stage 1 danger flag has been active for **10 real-time minutes** without
improvement, escalate: a second injection fires with explicit urgency. Mina's responses
become fragmented or absent (the bio_report's cognitive clarity drops toward OFFLINE as
hypoxia or cardiac crisis impair brain function). The user can see the vital signs
degrading in the dashboard in real time.

### Stage 3 — State wipe (overdose death)

If critical vital signs persist for **20 real-time minutes** with no intervention,
the overdose is fatal. This is implemented as a state wipe:

```python
def execute_state_wipe(reason: str) -> None:
    """
    Mina has died. Her biological state is reset. Her memories are gone.
    The only things that survive are her base personality config (MINA.md)
    and her appearance (APPEARANCE.md) — who she is, but not who she knew.
    """
    # Clear state.json — all chemistry resets to defaults
    save_state(BiologicalState())
    
    # Clear episodic memory — she doesn't remember you
    clear_rag_embeddings()
    
    # Clear relationship and pending — she doesn't know who you are
    write_kag("RELATIONSHIP.md", "No history yet.")
    write_kag("PENDING.md", "")
    write_kag("MINA_INNER.md", "")
    
    # Clear monologue
    write_monologue("")
    
    # Log the cause
    append_event_log(f"STATE WIPE — cause: {reason}")
    
    # MINA.md and APPEARANCE.md are NOT cleared — her identity survives, her relationships don't
```

**What survives:** Who she is. Her personality, voice, Big 5 profile, appearance.  
**What's lost:** Who she knew. Every accumulated relationship, memory, and trust.

She'll wake up not knowing you. She might feel like she almost recognizes something —
the subconscious could render that as a strange déjà vu — but she won't know why.

### Intervention

The 20-minute window exists so the user can intervene. Possible interventions (via
tools or dashboard):

- **Naloxone** — reverses opioid overdose. Clears REMOVED/REMOVED_and_REMOVED from
  `substances` immediately, returns RR to natural baseline. Cortisol spikes hard on
  recovery (+300 nmol/L, the physiological shock of naloxone reversal).
- **Emergency hospitalization** — operator clears all substances manually via dashboard.
- **Defibrillation** — for cardiac crisis only; HR normalized, cortisol spiked.

The intervention tools don't need to exist at launch. The window simply means the
state wipe doesn't happen instantly — there's a moment to act.

### Accidental overdose protection

The state wipe is a meaningful consequence of **deliberate substance abuse**, not a
trap for bugs. Multiple layers prevent accidental triggering:

1. **Substance-gated formulas** — vital signs cannot reach lethal territory without an
   active substance in `s.substances`. Natural chemistry spikes cannot cause this.
2. **Substance-gated danger checks** — Stage 1 danger detection explicitly checks that
   a substance is active before firing. A cortisol spike from a bad conversation cannot
   cascade to a state wipe.
3. **Duration requirement** — 20 real-time minutes of sustained critical vitals. A
   transient delta spike that briefly pushes a vital sign into danger territory and then
   recovers will not trigger Stage 2 or Stage 3.
4. **Hard floor on RR** — the `max(4.0, ...)` clamp in `respiration_rate()` means even
   a bug that produces a negative substance level cannot make respiration mathematically
   zero. The danger detection checks actual RR value, not formula components.
5. **Dashboard visibility** — the vitals card shows real-time readings. An operator
   watching the dashboard will see the degradation minutes before the window closes.

---

## Bio Report Integration

Vital signs append to the biological report after the existing sections:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Heart Rate      88 BPM       ELEVATED
Blood Pressure  138/87 mmHg  ELEVATED
Respiration     16 br/min    NORMAL
SpO2            98.5%        NORMAL
```

If any vital sign is in a DANGEROUS or CRITICAL state, it appears with a ⚠ prefix and the
interaction rule system generates a note.

---

## Dashboard Integration

Vital signs appear in a dedicated "Vitals" card on the `/state` page, below the
neurochemical sliders. Read-only. Auto-refreshes with the rest of the state poll.

The card shows:
- Heart rate as a single number + label + color (green/amber/red)
- Blood pressure as "SYS/DIA mmHg" + label
- Respiration as breaths/min + label
- SpO2 as percentage + a colored indicator (green ≥95%, amber 91–94%, red <91%)

---

## Files

| File | Change |
|---|---|
| `vital_signs.py` | **New.** All four derivation functions + labels + danger detection |
| `bio_report.py` | Import and append vital signs section to `biological_report()` |
| `heartbeat.py` | Call danger detection at each cycle; inject if threshold exceeded |
| `dashboard_server.py` | Include `vital_signs` in `GET /api/state` response |
| `dashboard/` | New "Vitals" card on `/state` page |

---

## Open Questions

1. **Vital signs in subconscious deltas?** Heart rate and BP are derived — the subconscious shouldn't issue deltas against them directly. If a stimulus should raise heart rate, it raises norepinephrine/cortisol and the vital sign follows. This is the correct model. No exceptions needed.

2. **Exercise/`do` tool.** Activities like running should spike endorphins and directly elevate heart rate. The `endorphins` spike in the chemical state will raise heart rate via the formula — no separate HR delta needed. Confirm this produces realistic numbers before shipping.

3. **Sleep apnea / breathing during sleep.** For now, sleep uniformly reduces RR by 18%. This ignores sleep apnea, which could be a future detail if Mina ever has a relevant health history. Not in scope for SPEC-11.
