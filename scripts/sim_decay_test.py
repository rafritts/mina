"""
Headless decay validation: runs the sim forward 24 sim-hours with no events,
sampling chemical state every sim-minute. Outputs a CSV to stdout and a
summary of which chemicals did/didn't return to baseline.

Usage:
    cd /home/restlessapi/workspace/mina
    python scripts/sim_decay_test.py > /tmp/decay_test.csv

Options (env vars):
    SIM_HOURS=48          how many sim-hours to run (default 24)
    TICK_MINUTES=1        sample interval in sim-minutes (default 1)
"""
from __future__ import annotations

import copy
import csv
import os
import sys
import time

# Make sure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.bio.state import load_state
from src.sim.engine import advance
from src.sim.chem.registry import REGISTRY

SIM_HOURS   = float(os.environ.get("SIM_HOURS",    24))
TICK_MINUTES = float(os.environ.get("TICK_MINUTES",  1))

TICK_SECONDS = TICK_MINUTES * 60.0
TICKS        = int(SIM_HOURS * 60 / TICK_MINUTES)

# Chemicals we care about (skip melatonin — it's pure circadian formula)
WATCH = [
    "serotonin", "dopamine", "oxytocin", "endorphins",
    "cortisol", "norepinephrine",
    "acetylcholine", "gaba", "glutamate",
]

BASELINES = {name: REGISTRY[name].resting_baseline for name in WATCH}


def main() -> None:
    state = load_state()
    # Freeze wall-clock time so we advance exactly TICK_SECONDS per tick
    # and don't drift with real time.
    now = time.time()

    writer = csv.writer(sys.stdout)
    header = ["sim_min"] + WATCH
    writer.writerow(header)

    # Record t=0
    row0 = [0] + [round(state.chemicals.get(n, 0.0), 3) for n in WATCH]
    writer.writerow(row0)

    for tick in range(1, TICKS + 1):
        now += TICK_SECONDS
        state = advance(state, now=now)
        sim_min = round(tick * TICK_MINUTES, 2)
        row = [sim_min] + [round(state.chemicals.get(n, 0.0), 3) for n in WATCH]
        writer.writerow(row)

    # Print summary to stderr so it doesn't pollute the CSV
    final = {n: state.chemicals.get(n, 0.0) for n in WATCH}
    print("\n=== DECAY SUMMARY (no-event 24h run) ===", file=sys.stderr)
    print(f"{'Chemical':<20} {'Start':>8} {'Baseline':>8} {'End':>8} {'Gap closed':>12}", file=sys.stderr)
    print("-" * 60, file=sys.stderr)

    # Re-load to get start values (we mutated state in-place above)
    start_state = load_state()

    for n in WATCH:
        start   = start_state.chemicals.get(n, 0.0)
        end     = final[n]
        baseline = BASELINES[n]
        initial_gap = start - baseline
        final_gap   = end   - baseline
        if abs(initial_gap) < 0.01:
            pct = "—  (at baseline)"
        else:
            pct_closed = (1.0 - final_gap / initial_gap) * 100.0
            pct = f"{pct_closed:+.1f}%"
        print(f"{n:<20} {start:>8.2f} {baseline:>8.2f} {end:>8.2f} {pct:>12}", file=sys.stderr)


if __name__ == "__main__":
    main()
