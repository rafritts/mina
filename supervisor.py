"""
Supervisor — owns the lifecycle of discord_gateway.py.

Exit code semantics from the child:
  42  → intentional restart (/restart, /reset) — no backoff
  0 + run/.stopped exists → maintenance stop — do not restart
  anything else → crash — exponential backoff

Run by systemd:
  ExecStart=uv run python supervisor.py
"""
import os
import subprocess
import sys
import time

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_RUN_DIR = os.path.join(_PROJECT_ROOT, "run")
_STOPPED_FLAG = os.path.join(_RUN_DIR, ".stopped")
_READY_FILE = os.path.join(_RUN_DIR, "ready")

RESTART_EXIT_CODE = 42
MAX_BACKOFF = 60  # seconds


def _backoff(n: int) -> float:
    return min(2 ** n, MAX_BACKOFF)


def _remove_ready():
    try:
        os.remove(_READY_FILE)
    except FileNotFoundError:
        pass


def main():
    os.makedirs(_RUN_DIR, exist_ok=True)

    uv = os.path.expanduser("~/.local/bin/uv")
    if not os.path.exists(uv):
        uv = "uv"

    cmd = [uv, "run", "python", "discord_gateway.py"]
    crashes = 0

    print(f"[SUPERVISOR] Starting: {' '.join(cmd)}", flush=True)

    while True:
        _remove_ready()

        proc = subprocess.Popen(cmd, cwd=_PROJECT_ROOT)
        rc = proc.wait()

        print(f"[SUPERVISOR] Child exited with code {rc}", flush=True)

        # Maintenance stop
        if os.path.exists(_STOPPED_FLAG):
            print("[SUPERVISOR] Stop flag detected — waiting for 'mina unstop'.", flush=True)
            while os.path.exists(_STOPPED_FLAG):
                time.sleep(5)
            print("[SUPERVISOR] Stop flag removed — restarting.", flush=True)
            crashes = 0
            continue

        # Intentional restart
        if rc == RESTART_EXIT_CODE:
            print("[SUPERVISOR] Intentional restart — no backoff.", flush=True)
            crashes = 0
            continue

        # Crash restart with backoff
        crashes += 1
        delay = _backoff(crashes)
        print(f"[SUPERVISOR] Crash #{crashes} — restarting in {delay:.0f}s.", flush=True)
        time.sleep(delay)


if __name__ == "__main__":
    main()
