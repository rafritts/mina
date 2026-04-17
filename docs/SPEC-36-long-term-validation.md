# SPEC-36: Long-Term Physiological Validation

## Problem

Mina's neurobiological simulation has been designed with real physiological units and calibrated constants, but its emergent behavior over time has never been systematically validated. We don't know whether chemical trajectories over days/weeks are realistic — whether cortisol drifts plausibly, whether sleep cycles produce correct adenosine dynamics, whether isolation deterioration stages actually manifest at the expected timeframes.

A week of conversation produces enough biological signal to either confirm the model or expose systematic errors (runaway accumulations, floors hit too fast, setpoints that never recover, etc.).

---

## Goal

Build a lightweight telemetry layer that logs enough state per heartbeat tick to reconstruct any chemical's trajectory over time, then provide tooling to validate those trajectories against physiological expectations.

---

## Design (to be detailed)

### Logging

- **Granularity**: Log full `BiologicalState` snapshot (or a curated subset of key markers) on every heartbeat tick (every 60s wall-clock).
- **Format**: Append-only JSONL file, one line per tick, with `ts` (ISO timestamp) and chemical values.
- **Storage**: `logs/bio_telemetry.jsonl` — rolling, configurable retention window (default: 30 days).
- **Key markers to capture at minimum**: all Tier 1 neurotransmitters, cortisol, adenosine, melatonin, orexin, allostatic_load, inflammation_index, isolation_pressure, hedonic_setpoint, sleep_state, glucose.

### Validation Script

A standalone script `tools/validate_physiology.py` that:

1. Reads `logs/bio_telemetry.jsonl` over a user-specified window (default: last 7 days)
2. Computes per-chemical statistics: mean, std, min, max, time-at-floor, time-at-ceiling, recovery half-life (empirical)
3. Compares against expected physiological ranges defined in `src/sim/constants.py`
4. Flags anomalies:
   - Chemical stuck at floor/ceiling for >N hours
   - Mean value >2 SD outside resting baseline over any 48h window
   - Cortisol CAR (cortisol awakening response) absent or inverted vs. expected post-sleep rise
   - Adenosine not clearing to baseline within sleep window
   - Serotonin mean trending monotonically down over 7 days (isolation deterioration check)
5. Outputs a human-readable report + optional charts (matplotlib, optional dependency)

### Circadian Validation

Sleep-wake cycles are the most testable output. The validator should reconstruct Mina's sleep/wake timeline and check:
- Sleep duration per cycle vs. `sleep_hours_needed` config
- Adenosine floor reached during sleep (confirming Process S clearance)
- Melatonin peak timing vs. expected circadian phase

### Open Questions

- Should telemetry be opt-in or always-on? (Prefer always-on with configurable retention)
- Should the validator be a CLI tool or integrated into the dashboard?
- Do we want per-conversation-session tagging in telemetry, or pure time-series?
- Alerting: should persistent anomalies surface in the Discord channel or stay silent?

---

## Validation Targets (to be filled in during implementation)

| Chemical | Expected range | Anomaly threshold |
|---|---|---|
| Cortisol | 140–560 nmol/L (awake) | >600 sustained >4h |
| Adenosine | ~20 baseline, ~80 at sleep onset | Never clearing below 30 during sleep |
| Serotonin | 18–26 ng/mL healthy range | <14 sustained >24h |
| Dopamine | 70–110 pg/mL resting | >180 sustained >2h or <30 sustained >6h |
| Allostatic load | 0–100, healthy <40 | >70 sustained >72h |

---

## Status

Flag planted. Implementation pending.
