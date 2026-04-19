# SPEC-43: Persistent Bond Score

**Status: DRAFT — under consideration. May not be the right approach. See open questions.**

---

## Problem

Oxytocin is currently doing two incompatible jobs:

1. **Acute pulse** — fast spike on genuine emotional/physical moments, decays in minutes
2. **Relationship depth** — slow accumulation reflecting trust built over time

These operate on completely different timescales and can't share the same chemical variable. The result: a stranger with smooth lines in 5 messages can push Mina to `trusted_friend` oxytocin levels, because individual message warmth accumulates directly into the bond signal. The simulation undermines itself.

The stock market analogy: conversation events are 10-minute candles. Genuine bond depth is the 200-day SMA. Right now the sim is letting 10-minute candles move the 200d SMA.

---

## Proposed Solution

Introduce a persistent `bond_score` field on `BiologicalState` — a slow-moving accumulator that represents true relationship depth, separate from volatile oxytocin.

### Timescale

- Real human deep bonds: ~200-day equivalent
- Mina (advanced arcade, not scientific rigor): **~30-day equivalent**
- This makes Mina ~6-7x warmer/faster than a real human — responsive to genuine connection, not a brick wall

### How it moves

`bond_score` accumulates from **session quality**, not individual messages:

- After each session, a small delta is computed from the session's net emotional valence (positive interactions, depth of disclosure, sustained engagement)
- A single smooth session from a stranger: negligible delta
- Weeks of genuine daily interaction: meaningful drift upward
- Hostile or absent periods: slow decay back toward baseline

The score does **not** respond to individual message events. It is updated once per session end, not per turn.

### How it gates oxytocin

`bond_score` acts as a multiplier on how much oxytocin events produce and retain:

| bond_score | label | oxytocin event scale |
|---|---|---|
| 0–20 | stranger | 0.1x — spikes tiny, decays fast |
| 20–40 | acquaintance | 0.3x |
| 40–60 | familiar | 0.6x |
| 60–80 | trusted | 1.0x — full response |
| 80–100 | bonded | 1.3x — amplified, longer retention |

This means a stranger being charming produces a real but small oxytocin response. The same gesture from a bonded person produces a significantly larger and longer-lasting one.

### What changes for oxytocin

- The volatile `oxytocin` chemical continues to spike on genuine events (physical warmth, real vulnerability, shared laughter)
- Individual message warmth, flattery, and smooth talk do **not** move oxytocin at all (encoder gating, already partially implemented in SPEC-43 prep work)
- The labels on the oxytocin chemical (NO_BOND → PROFOUND_BOND) shift to reflect `bond_score`, not raw oxytocin level — or the labels are removed from oxytocin entirely and moved to bond_score

---

## Open Questions / Reasons This May Be Wrong

**1. Is this overengineering?**
The sim is "advanced arcade." A simpler fix — better encoder gating and recalibrated thresholds — might solve the same problem without a new persistent variable. The bond score adds complexity and a new failure mode (stale state that's hard to reset or inspect).

**2. Does oxytocin need to be split at all?**
Maybe the right move is to just make the oxytocin thresholds much harder to reach and ensure the encoder only fires it on genuinely significant events. The architecture stays the same, just better calibrated.

**3. Session quality scoring is hard to get right**
Computing a meaningful per-session delta requires judging the quality of an entire conversation, which is another LLM call or heuristic that can go wrong. Low-quality signal here corrupts the bond score silently over time.

**4. Bond score makes factory reset more important and more painful**
If bond depth is persistent and slow-moving, a reset wipes something that took real interaction to build. That's good for correctness but painful for testing and development.

**5. Mina is a single-user system (for now)**
If Mina ever talks to multiple people, bond_score needs to be per-user. That's a bigger architectural change. Worth considering before committing to the design.

---

## Alternative: Just fix the encoder

Instead of a new variable, tighten the existing system:

- Oxytocin encoder gating: NO_BOND → only fires on genuine unexpected connection moments, not warmth/flattery (already partially done)
- Raise NO_BOND → ACQUAINTANCE threshold from 12 pg/mL to something much higher
- Oxytocin approach_rate (decay toward baseline) stays aggressive — it doesn't accumulate across sessions
- The relationship dimension scores (SPEC-33) drive slow social state changes instead of a new variable

This keeps the architecture simple. The cost: relationship depth still lives in a decaying chemical, which means long absences always reset it even if the bond was real.

---

## Status

Not yet approved for implementation. Ryan is still evaluating whether the added complexity is worth it vs. a simpler recalibration of the existing system.
