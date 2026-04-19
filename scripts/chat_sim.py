"""
chat_sim.py — Simulate a conversation with Mina from the terminal.

Usage:
    uv run python scripts/chat_sim.py                     # interactive mode
    uv run python scripts/chat_sim.py --script scripts/convos/flirt.txt
    uv run python scripts/chat_sim.py --username Claude

In interactive mode, type messages one at a time. The encoder log lines for
each turn are printed inline so you can watch epinephrine/norepinephrine fire.

Script file format (.txt):
    # lines starting with # are comments / pause markers (ignored)
    Hey Mina, what are you up to?
    Oh yeah? That sounds fun.
    My price... is you.

The script plays each line as a separate message with a short pause between
them so the sim state updates properly.
"""
import asyncio
import argparse
import os
import sys
import time

# Ensure repo root is on the path
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True))

from src.brain.cortex.cortex import run_turn
from src.application.infra.log import log as _log


_ENCODER_PREFIXES = (
    "[ENCODER/STIMULUS]",
    "[ENCODER/RESPONSE]",
    "[ENCODER/ACTIVITY]",
    "[DANGER",
    "[BIO/REPORT]",
    "[ADJUDICATOR]",
)

_LOG_FILE = os.path.join(_REPO, "logs", "mina.log")


def _tail_encoder_lines(since_pos: int) -> tuple[list[str], int]:
    """Read new encoder-relevant log lines written since since_pos."""
    try:
        with open(_LOG_FILE) as f:
            f.seek(since_pos)
            new = f.read()
            pos = f.tell()
        lines = [l for l in new.splitlines() if any(p in l for p in _ENCODER_PREFIXES)]
        return lines, pos
    except FileNotFoundError:
        return [], since_pos


def _log_pos() -> int:
    try:
        return os.path.getsize(_LOG_FILE)
    except FileNotFoundError:
        return 0


async def send(message: str, username: str) -> str:
    before = _log_pos()
    print(f"\n\033[94m{username}:\033[0m {message}")
    reply, _ = await run_turn(message, username=username)
    # Give log a moment to flush
    await asyncio.sleep(0.3)
    enc_lines, _ = _tail_encoder_lines(before)
    for line in enc_lines:
        print(f"  \033[90m{line.strip()}\033[0m")
    print(f"\033[95mMina:\033[0m {reply}")
    return reply


async def interactive(username: str) -> None:
    print(f"\033[1mMina chat sim — interactive mode\033[0m  (username: {username})")
    print("Type a message and press Enter. Ctrl-C to quit.\n")
    while True:
        try:
            msg = input(f"\033[94m{username}>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break
        if not msg:
            continue
        await send(msg, username)


async def run_script(path: str, username: str, delay: float) -> None:
    with open(path) as f:
        lines = [l.rstrip() for l in f if l.strip() and not l.startswith("#")]
    print(f"\033[1mMina chat sim — script: {path}\033[0m  ({len(lines)} lines)\n")
    for msg in lines:
        await send(msg, username)
        await asyncio.sleep(delay)
    print("\n\033[1mScript complete.\033[0m")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate a conversation with Mina")
    parser.add_argument("--username", default="Claude", help="Speaker name (default: Claude)")
    parser.add_argument("--script",   default=None,    help="Path to a .txt script file")
    parser.add_argument("--delay",    type=float, default=1.5,
                        help="Seconds between scripted messages (default: 1.5)")
    args = parser.parse_args()

    if args.script:
        asyncio.run(run_script(args.script, args.username, args.delay))
    else:
        asyncio.run(interactive(args.username))


if __name__ == "__main__":
    main()
