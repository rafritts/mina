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
import datetime
import os
import sys
import time

# Ensure repo root is on the path
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True))

# Patch log() to write to mina.log so _tail_encoder_lines can read it.
# The gateway normally does this via stdout redirect; chat_sim runs standalone.
import src.application.infra.log as _log_module
_orig_log = _log_module.log
_LOG_FILE = os.path.join(_REPO, "logs", "mina.log")
_log_fh = open(_LOG_FILE, "a", buffering=1)

def _patched_log(tag: str, msg: str = "") -> None:
    _orig_log(tag, msg)
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] [{tag}] {msg}" if msg else f"[{ts}] [{tag}]"
    _log_fh.write(line + "\n")

_log_module.log = _patched_log

from src.brain.cortex.cortex import run_turn


_ENCODER_PREFIXES = (
    "[ENCODER/STIMULUS]",
    "[ENCODER/RESPONSE]",
    "[ENCODER/ACTIVITY]",
    "[DANGER",
    "[BIO/PROFILE]",
    "[ADJUDICATOR]",
)

_OUTPUT_DIR = os.path.join(_REPO, "run", "script_output")


def _open_output(label: str):
    """Return an open file handle for this run's output, or None on failure."""
    try:
        os.makedirs(_OUTPUT_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{ts}_{label}.txt"
        return open(os.path.join(_OUTPUT_DIR, name), "w", buffering=1)
    except Exception:
        return None


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


async def send(message: str, username: str, out=None) -> str:
    before = _log_pos()
    header = f"\n{username}: {message}"
    print(f"\n\033[94m{username}:\033[0m {message}")
    if out:
        out.write(header + "\n")
    reply, _ = await run_turn(message, username=username)
    # Give log a moment to flush
    await asyncio.sleep(0.3)
    enc_lines, _ = _tail_encoder_lines(before)
    for line in enc_lines:
        print(f"  \033[90m{line.strip()}\033[0m")
        if out:
            out.write(f"  {line.strip()}\n")
    mina_line = f"Mina: {reply}"
    print(f"\033[95mMina:\033[0m {reply}")
    if out:
        out.write(mina_line + "\n")
    return reply


async def interactive(username: str) -> None:
    print(f"\033[1mMina chat sim — interactive mode\033[0m  (username: {username})")
    print("Type a message and press Enter. Ctrl-C to quit.\n")
    out = _open_output(f"interactive_{username}")
    while True:
        try:
            msg = input(f"\033[94m{username}>\033[0m ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break
        if not msg:
            continue
        await send(msg, username, out)
    if out:
        out.close()


async def run_script(path: str, username: str, delay: float) -> None:
    with open(path) as f:
        lines = [l.rstrip() for l in f if l.strip() and not l.startswith("#")]
    script_name = os.path.splitext(os.path.basename(path))[0]
    header = f"Mina chat sim — script: {path}  ({len(lines)} lines)"
    print(f"\033[1m{header}\033[0m\n")
    out = _open_output(script_name)
    if out:
        out.write(header + "\n\n")
    for msg in lines:
        await send(msg, username, out)
        await asyncio.sleep(delay)
    print("\n\033[1mScript complete.\033[0m")
    if out:
        out.write("\nScript complete.\n")
        out.close()
        print(f"Output saved to {_OUTPUT_DIR}/")


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
