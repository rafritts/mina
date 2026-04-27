"""
SPEC-53: Headless resting-state validator.

Advances the biological engine through N ticks of pure math — no LLM calls,
no stimuli, no encoder — and checks that every chemical settles near its
resting baseline.

Usage:
    python -m src.application.tools.sim_baseline
    python -m src.application.tools.sim_baseline --ticks 10000 --step 0.05
    python -m src.application.tools.sim_baseline --ticks 50000 --step 0.1 --chemical cortisol

--step     sim-hours per tick (default 0.05 = 3 sim-minutes)
--ticks    number of ticks to run (default 10000)
--chemical run validator for a single chemical and print full history
--seed     integer RNG seed for reproducible noise (default: no seed)
"""
from __future__ import annotations

import argparse
import math
import random
import sys
import time


def _run(ticks: int, step: float, chemical: str | None, seed: int | None) -> None:
    from src.engine.bio.state import BiologicalState
    from src.engine.engine import advance
    from src.engine.chem.registry import REGISTRY
    from src.engine.bio.defaults import CHEMICAL_DEFAULTS

    if seed is not None:
        random.seed(seed)

    state = BiologicalState()
    now = time.time()

    # Tracking: per-chemical history
    history: dict[str, list[float]] = {name: [] for name in REGISTRY}

    for tick in range(ticks):
        now += step * 3600.0
        state = advance(state, now=now)
        for name in REGISTRY:
            val = state.chemicals.get(name, CHEMICAL_DEFAULTS.get(name, 0.0))
            history[name].append(val)

    # If single-chemical mode, print full history and exit
    if chemical:
        if chemical not in history:
            print(f"Unknown chemical: {chemical}", file=sys.stderr)
            sys.exit(1)
        profile = REGISTRY[chemical]
        print(f"# {profile.display_name} ({profile.unit}) — {ticks} ticks @ {step}h each")
        print(f"# clearance={profile.clearance}  half_life={profile.plasma_half_life}min  "
              f"resting_baseline={profile.resting_baseline}  noise_sigma={profile.noise_sigma}")
        print(f"tick,value")
        for i, v in enumerate(history[chemical]):
            print(f"{i},{v:.4f}")
        return

    # Full report
    print(f"Sim baseline validator — {ticks} ticks @ {step}h/tick  "
          f"({'seeded: ' + str(seed) if seed is not None else 'random noise'})")
    print()
    print(f"{'STATUS':<6}  {'CHEMICAL':<16}  {'SETTLED':>10}  {'EXPECTED':>10}  {'DRIFT':>8}  {'STDDEV':>8}  NOTES")
    print("-" * 80)

    for name, profile in REGISTRY.items():
        vals = history[name]
        if not vals:
            continue

        # Use last 500 ticks as "settled" window (rolling mean per spec)
        window = vals[-500:] if len(vals) >= 500 else vals
        mean = sum(window) / len(window)
        variance = sum((v - mean) ** 2 for v in window) / len(window)
        stddev = math.sqrt(variance)
        final = vals[-1]
        min_val = min(vals)
        max_val = max(vals)

        # Formula chemicals: range check only
        if profile.clearance == "formula":
            lo = profile.resting_low
            hi = profile.resting_high if profile.resting_high > 0 else profile.critical_high
            if lo <= min_val and max_val <= hi:
                status = "WARN "
                note = f"[circadian — peak={max_val:.1f} trough={min_val:.1f}]"
            else:
                status = "WARN "
                note = f"[circadian — peak={max_val:.1f} trough={min_val:.1f}, OUTSIDE resting range {lo}–{hi}]"
            print(f"{status}  {name:<16}  {mean:>10.2f}  {'N/A':>10}  {'N/A':>8}  {stddev:>8.3f}  {note}")
            continue

        # Determine expected resting value
        expected = profile.resting_baseline if profile.resting_baseline > 0 else None

        flags = []
        if profile.critical_low > 0 and min_val <= profile.critical_low:
            flags.append("HIT CRITICAL_LOW")
        if profile.critical_high > 0 and max_val >= profile.critical_high:
            flags.append("HIT CRITICAL_HIGH")

        if expected is not None and expected > 0:
            drift_pct = (mean - expected) / expected * 100.0
            lo = profile.resting_low
            hi = profile.resting_high
            outside_resting = (lo > 0 and mean < lo) or (hi > 0 and mean > hi)

            # Check for monotonic drift (never stabilized)
            if len(vals) > 100:
                first_half = sum(vals[:len(vals)//2]) / (len(vals)//2)
                second_half = sum(vals[len(vals)//2:]) / (len(vals) - len(vals)//2)
                monotonic = abs(second_half - first_half) > abs(mean - (expected or mean)) * 0.5

                # Oscillation check: high stddev relative to mean
                oscillating = stddev > abs(mean) * 0.3 and mean > 0
            else:
                monotonic = False
                oscillating = False

            if flags or outside_resting or monotonic:
                status = "FAIL "
                if outside_resting:
                    flags.append(f"outside resting range [{lo}–{hi}]")
                if monotonic:
                    flags.append("monotonic drift")
            else:
                status = "PASS "

            note = "  ".join(flags) if flags else ""
            print(f"{status}  {name:<16}  {mean:>10.2f}  {expected:>10.1f}  "
                  f"{drift_pct:>+7.1f}%  {stddev:>8.3f}  {note}")
        else:
            # No expected baseline (hydration, glucose, etc.) — just report
            note = "  ".join(flags) if flags else "[no baseline]"
            print(f"{'INFO ':<6}  {name:<16}  {mean:>10.2f}  {'—':>10}  {'—':>8}  {stddev:>8.3f}  {note}")

    print()
    print(f"Rolling mean window: last {min(500, ticks)} ticks of {ticks}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sim resting-state baseline validator")
    parser.add_argument("--ticks",    type=int,   default=10000,  help="Number of ticks to run")
    parser.add_argument("--step",     type=float, default=0.05,   help="Sim-hours per tick")
    parser.add_argument("--chemical", type=str,   default=None,   help="Single chemical CSV mode")
    parser.add_argument("--seed",     type=int,   default=None,   help="RNG seed for reproducibility")
    args = parser.parse_args()
    _run(args.ticks, args.step, args.chemical, args.seed)


if __name__ == "__main__":
    main()
