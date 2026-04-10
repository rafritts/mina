"""
Supervisor — owns the lifecycle of discord_gateway.py and dashboard_server.py.

Exit code semantics from the child (discord_gateway only):
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
import threading
import time

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_RUN_DIR = os.path.join(_PROJECT_ROOT, "run")
_LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "mina.log")
_CONV_FILE = os.path.join(_RUN_DIR, "conversation.json")
_STOPPED_FLAG = os.path.join(_RUN_DIR, ".stopped")
_READY_FILE = os.path.join(_RUN_DIR, "ready")

RESTART_EXIT_CODE = 42
MAX_BACKOFF = 60       # seconds
LOG_ARCHIVE_KEEP = 10  # keep last N session tombstones


# ---------------------------------------------------------------------------
# Log file management
# ---------------------------------------------------------------------------

def _tombstone_log() -> None:
    """Archive mina.log and conversation.json as timestamped session files. No-op if absent/empty."""
    ts = time.strftime("%Y%m%dT%H%M%S")
    if os.path.exists(_LOG_FILE) and os.path.getsize(_LOG_FILE) > 0:
        os.rename(_LOG_FILE, os.path.join(_LOG_DIR, f"mina-{ts}.log"))
    if os.path.exists(_CONV_FILE) and os.path.getsize(_CONV_FILE) > 2:
        os.rename(_CONV_FILE, os.path.join(_LOG_DIR, f"conversation-{ts}.json"))
    _prune_tombstones()


def _prune_tombstones() -> None:
    """Remove oldest session tombstones beyond LOG_ARCHIVE_KEEP."""
    if not os.path.exists(_LOG_DIR):
        return
    for prefix, suffix in [("mina-", ".log"), ("conversation-", ".json")]:
        archives = sorted(
            f for f in os.listdir(_LOG_DIR)
            if f.startswith(prefix) and f.endswith(suffix)
        )
        for old in archives[:-LOG_ARCHIVE_KEEP] if len(archives) > LOG_ARCHIVE_KEEP else []:
            try:
                os.remove(os.path.join(_LOG_DIR, old))
            except OSError:
                pass


def _open_log():
    os.makedirs(_LOG_DIR, exist_ok=True)
    _tombstone_log()
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

_DASHBOARD_PORT = 7843
_dashboard_proc: subprocess.Popen | None = None


def _free_port(port: int) -> None:
    """Kill any process holding the given TCP port (best-effort)."""
    try:
        result = subprocess.run(
            ["fuser", f"{port}/tcp"],
            capture_output=True, text=True
        )
        for pid_str in result.stdout.split():
            try:
                os.kill(int(pid_str), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass
        if result.stdout.strip():
            time.sleep(0.5)  # give the old process a moment to release the port
    except FileNotFoundError:
        pass  # fuser not available — skip


def _run_dashboard(uv: str, tee_out) -> None:
    """
    Run dashboard_server.py in a background thread with simple restart-on-crash.
    Uses tee_out._log (not a captured log_f) so it always writes to the current
    log file even after a gateway restart rotates the log.
    Stops when the supervisor exits (daemon thread).
    """
    global _dashboard_proc
    cmd = [uv, "run", "python", "-u", "dashboard_server.py"]
    backoff = 5
    while True:
        _free_port(_DASHBOARD_PORT)
        try:
            _log("[DASHBOARD] Starting dashboard server.", tee_out)
            _dashboard_proc = subprocess.Popen(cmd, cwd=_PROJECT_ROOT, stdout=tee_out._log, stderr=tee_out._log)
            rc = _dashboard_proc.wait()
            _dashboard_proc = None
            _log(f"[DASHBOARD] Exited with code {rc} — restarting in {backoff}s.", tee_out)
        except Exception as e:
            _dashboard_proc = None
            _log(f"[DASHBOARD] Launch error: {e} — retrying in {backoff}s.", tee_out)
        time.sleep(backoff)


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

    # Start dashboard server as a daemon thread — auto-restarts on crash
    dashboard_thread = threading.Thread(
        target=_run_dashboard, args=(uv, tee_out), daemon=True
    )
    dashboard_thread.start()

    cmd = [uv, "run", "python", "-u", "discord_gateway.py"]
    crashes = 0
    current_proc = None

    def _handle_sigterm(signum, frame):
        """Kill the child and exit cleanly when systemd stops the service."""
        # Kill dashboard first so the port is free if supervisor immediately restarts
        if _dashboard_proc and _dashboard_proc.poll() is None:
            _dashboard_proc.terminate()
            try:
                _dashboard_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                _dashboard_proc.kill()
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
