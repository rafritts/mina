"""
factory_reset.py — Standalone factory reset for Mina (no bot required).

Usage:
    uv run python scripts/factory_reset.py            # soft reset: convos, KAG, RAG
    uv run python scripts/factory_reset.py --full     # + biomarkers (state.json)
    uv run python scripts/factory_reset.py --log      # also truncate logs/mina.log
    uv run python scripts/factory_reset.py --full --log

Equivalent to the Discord /factory-reset command but runs standalone so you
can reset between sim runs without Discord. Does NOT restart any running process.
"""
import argparse
import glob
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True))

_RUN_DIR  = os.path.join(_REPO, "run")
_LOG_FILE = os.path.join(_REPO, "logs", "mina.log")


def _wipe_run_files() -> list[str]:
    wiped = []

    static = [
        "run/conversation.json",
        "run/conversation.json.archived",
        "run/decoder_window.json",
        "run/decoder_history.jsonl",
        "run/bio_snapshots.jsonl",
        "run/last_search.json",
        "run/consolidation_state.json",
        "run/bio_history.jsonl",
    ]
    daily = [
        os.path.relpath(p, _REPO).replace(os.sep, "/")
        for p in glob.glob(os.path.join(_RUN_DIR, "conversation-*.jsonl"))
    ]

    for rel in static + daily:
        dst = os.path.join(_REPO, rel)
        if os.path.exists(dst):
            os.remove(dst)
            wiped.append(rel)

    return wiped


def _wipe_kag() -> list[str]:
    wiped = []
    kag_dir = os.path.join(_REPO, "memory", "kag")
    if os.path.exists(kag_dir):
        for root, _dirs, files in os.walk(kag_dir):
            for fname in files:
                full = os.path.join(root, fname)
                os.remove(full)
                wiped.append(os.path.relpath(full, _REPO).replace(os.sep, "/"))
    os.makedirs(kag_dir, exist_ok=True)
    return wiped


def _wipe_rag() -> str:
    from src.brain.hippocampus.hippocampus import rag_wipe
    try:
        rag_wipe()
        return "memory/rag/ (wiped)"
    except Exception as e:
        return f"memory/rag/ (wipe failed: {e})"


def _reset_biomarkers() -> str:
    from src.brain.brainstem.state import BiologicalState, save_state
    save_state(BiologicalState())
    return "run/state.json (biomarkers reset to defaults)"


def _truncate_log() -> str:
    try:
        open(_LOG_FILE, "w").close()
        return f"logs/mina.log (truncated)"
    except Exception as e:
        return f"logs/mina.log (truncate failed: {e})"


def main() -> None:
    parser = argparse.ArgumentParser(description="Factory reset Mina")
    parser.add_argument("--full", action="store_true",
                        help="Also reset biomarkers (state.json) to defaults")
    parser.add_argument("--log",  action="store_true",
                        help="Also truncate logs/mina.log")
    args = parser.parse_args()

    print("Resetting Mina...\n")
    wiped: list[str] = []

    wiped += _wipe_run_files()
    wiped += _wipe_kag()
    wiped.append(_wipe_rag())

    if args.full:
        wiped.append(_reset_biomarkers())

    if args.log:
        wiped.append(_truncate_log())

    for entry in wiped:
        print(f"  \033[90m{entry}\033[0m")

    label = "Factory reset" if args.full else "Reset"
    print(f"\n\033[1m{label} complete.\033[0m")
    if not args.full:
        print("  (biomarkers preserved — run with --full to also reset state.json)")


if __name__ == "__main__":
    main()
