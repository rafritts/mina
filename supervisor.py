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
import signal
import subprocess
import sys
import time

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_RUN_DIR = os.path.join(_PROJECT_ROOT, "run")
_LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "mina.log")
_STOPPED_FLAG = os.path.join(_RUN_DIR, ".stopped")
_READY_FILE = os.path.join(_RUN_DIR, "ready")

RESTART_EXIT_CODE = 42
MAX_BACKOFF = 60       # seconds
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB per file
LOG_KEEP = 3


# ---------------------------------------------------------------------------
# Log file management
# ---------------------------------------------------------------------------

def _rotate_log():
    if not os.path.exists(_LOG_FILE):
        return
    if os.path.getsize(_LOG_FILE) < LOG_MAX_BYTES:
        return
    for i in range(LOG_KEEP - 1, 0, -1):
        src = f"{_LOG_FILE}.{i}"
        dst = f"{_LOG_FILE}.{i + 1}"
        if os.path.exists(src):
            os.rename(src, dst)
    os.rename(_LOG_FILE, f"{_LOG_FILE}.1")


def _open_log():
    os.makedirs(_LOG_DIR, exist_ok=True)
    _rotate_log()
    # Line-buffered so writes appear immediately
    return open(_LOG_FILE, "a", buffering=1, encoding="utf-8")


class _Tee:
    """Write to both a file and the original stream (so journald still gets it)."""
    def __init__(self, stream, log_file):
        self._stream = stream
        self._log = log_file

    def write(self, data):
        self._stream.write(data)
        self._stream.flush()
        self._log.write(data)

    def flush(self):
        self._stream.flush()
        self._log.flush()

    def fileno(self):
        # Popen needs a real fd for stdout/stderr — return the log file's fd
        return self._log.fileno()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _backoff(n: int) -> float:
    return min(2 ** n, MAX_BACKOFF)


def _remove_ready():
    try:
        os.remove(_READY_FILE)
    except FileNotFoundError:
        pass


def _log(msg: str, tee) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    tee.write(line)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(_RUN_DIR, exist_ok=True)

    log_f = _open_log()
    tee_out = _Tee(sys.stdout, log_f)
    tee_err = _Tee(sys.stderr, log_f)

    # Replace stdout/stderr so our own prints also land in the log file
    sys.stdout = tee_out
    sys.stderr = tee_err

    uv = os.path.expanduser("~/.local/bin/uv")
    if not os.path.exists(uv):
        uv = "uv"

    cmd = [uv, "run", "python", "discord_gateway.py"]
    crashes = 0
    current_proc = None

    def _handle_sigterm(signum, frame):
        """Kill the child and exit cleanly when systemd stops the service."""
        if current_proc and current_proc.poll() is None:
            _log("[SUPERVISOR] SIGTERM received — killing child.", tee_out)
            current_proc.terminate()
            try:
                current_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                current_proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    _log(f"[SUPERVISOR] Starting: {' '.join(cmd)}", tee_out)

    while True:
        _remove_ready()

        # Child stdout/stderr go to the same log file
        current_proc = subprocess.Popen(cmd, cwd=_PROJECT_ROOT, stdout=log_f, stderr=log_f)
        rc = current_proc.wait()

        _log(f"[SUPERVISOR] Child exited with code {rc}", tee_out)

        # Maintenance stop
        if os.path.exists(_STOPPED_FLAG):
            _log("[SUPERVISOR] Stop flag detected — waiting for 'mina unstop'.", tee_out)
            while os.path.exists(_STOPPED_FLAG):
                time.sleep(5)
            _log("[SUPERVISOR] Stop flag removed — restarting.", tee_out)
            crashes = 0
            continue

        # Intentional restart
        if rc == RESTART_EXIT_CODE:
            _log("[SUPERVISOR] Intentional restart — no backoff.", tee_out)
            crashes = 0
            log_f.close()
            log_f = _open_log()
            tee_out._log = log_f
            tee_err._log = log_f
            continue

        # Crash restart with backoff
        crashes += 1
        delay = _backoff(crashes)
        _log(f"[SUPERVISOR] Crash #{crashes} — restarting in {delay:.0f}s.", tee_out)
        time.sleep(delay)


if __name__ == "__main__":
    main()
