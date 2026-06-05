"""
Print full turn logs.

Usage:
    uv run python scripts/turns.py           # all turns
    uv run python scripts/turns.py -n 3      # last N turns
"""
import argparse
import json
import sys
from pathlib import Path

TURNS_FILE = Path(__file__).parents[1] / "run" / "turns.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=0, help="Last N turns (0 = all)")
    args = parser.parse_args()

    if not TURNS_FILE.exists():
        print(f"No turns log found at {TURNS_FILE}", file=sys.stderr)
        sys.exit(1)

    records = []
    with open(TURNS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if args.n > 0:
        records = records[-args.n:]

    for r in records:
        print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
