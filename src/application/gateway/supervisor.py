"""
Supervisor — owns the lifecycle of discord_gateway.py and dashboard_server.py.

Exit code semantics from the child (discord_gateway only):
  42  → intentional restart (/restart, /reset) — no backoff
  0 + run/.stopped exists → maintenance stop — do not restart
  anything else → crash — exponential backoff

Run by systemd:
  ExecStart=uv run python -m src.application.gateway.supervisor
"""
import os
import signal
import subprocess
import sys
import threading
import time

from dotenv import load_dotenv, find_dotenv

_DOTENV = find_dotenv(usecwd=True)
load_dotenv(_DOTENV)
_PROJECT_ROOT = os.path.dirname(_DOTENV)
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
    """Archive mina.log as a timestamped session file. No-op if absent/empty.
    conversation.json is intentionally NOT archived — it persists across restarts
    so Mode 2 (heartbeat reflection) always has access to recent history.
    It is bounded by HISTORY_MAX in main.py."""
    ts = time.strftime("%Y%m%dT%H%M%S")
    if os.path.exists(_LOG_FILE) and os.path.getsize(_LOG_FILE) > 0:
        os.rename(_LOG_FILE, os.path.join(_LOG_DIR, f"mina-{ts}.log"))
    _prune_tombstones()


def _prune_tombstones() -> None:
    """Remove oldest log tombstones beyond LOG_ARCHIVE_KEEP."""
    if not os.path.exists(_LOG_DIR):
        return
    archives = sorted(
        f for f in os.listdir(_LOG_DIR)
        if f.startswith("mina-") and f.endswith(".log")
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

_DASHBOARD_PORT = 2049
_UI_PORT = 2050
_dashboard_proc: subprocess.Popen | None = None
_ui_proc: subprocess.Popen | None = None

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
    Opens a fresh binary file handle to the log path on each launch so there is
    never a stale/closed fd issue regardless of log rotation.
    Stops when the supervisor exits (daemon thread).
    """
    global _dashboard_proc
    cmd = [uv, "run", "python", "-u", "-m", "src.application.gateway.dashboard_server"]
    backoff = 5
    while True:
        _free_port(_DASHBOARD_PORT)
        try:
            _log("[DASHBOARD] Starting dashboard server.", tee_out)
            # Open a fresh binary handle each launch; close parent copy immediately
            # after Popen — the child inherits its own copy via dup2.
            dash_log = open(_LOG_FILE, "ab")
            _dashboard_proc = subprocess.Popen(cmd, cwd=_PROJECT_ROOT, stdout=dash_log, stderr=dash_log)
            dash_log.close()
            rc = _dashboard_proc.wait()
            _dashboard_proc = None
            _log(f"[DASHBOARD] Exited with code {rc} — restarting in {backoff}s.", tee_out)
        except Exception as e:
            _dashboard_proc = None
            _log(f"[DASHBOARD] Launch error: {e} — retrying in {backoff}s.", tee_out)
        time.sleep(backoff)


def _run_ui(tee_out) -> None:
    """
    Run the Next.js admin UI on port 2050.

    Production mode: `node .next/standalone/server.js` (requires `npm run build` first).
    Falls back to `npm run dev` if the standalone build is absent — useful during
    development before the first build.

    Stops when the supervisor exits (daemon thread).
    """
    global _ui_proc
    _UI_DIR = os.path.join(_PROJECT_ROOT, "ui")
    standalone = os.path.join(_UI_DIR, ".next", "standalone", "server.js")
    backoff = 5

    # Resolve node/npm — check Linuxbrew and nvm locations that systemd won't have in PATH
    def _find_bin(name: str) -> str:
        candidates = [
            f"/home/linuxbrew/.linuxbrew/bin/{name}",
            os.path.expanduser(f"~/.nvm/versions/node/$(ls ~/.nvm/versions/node 2>/dev/null | tail -1)/bin/{name}"),
            f"/usr/local/bin/{name}",
            f"/usr/bin/{name}",
            name,  # last resort: rely on PATH
        ]
        for c in candidates:
            if os.path.isfile(c) and os.access(c, os.X_OK):
                return c
        return name

    node = _find_bin("node")
    npm  = _find_bin("npm")

    while True:
        _free_port(_UI_PORT)
        env = {**os.environ, "PORT": str(_UI_PORT), "HOSTNAME": "0.0.0.0"}
        try:
            if os.path.exists(standalone):
                cmd = [node, standalone]
                label = "production"
            else:
                # Dev server — slow cold start but always works without a pre-build
                cmd = [npm, "run", "dev", "--", "--port", str(_UI_PORT)]
                label = "dev"

            _log(f"[UI] Starting Next.js UI ({label}) on :{_UI_PORT}.", tee_out)
            ui_log = open(_LOG_FILE, "ab")
            _ui_proc = subprocess.Popen(cmd, cwd=_UI_DIR, stdout=ui_log, stderr=ui_log, env=env)
            ui_log.close()
            rc = _ui_proc.wait()
            _ui_proc = None
            _log(f"[UI] Exited with code {rc} — restarting in {backoff}s.", tee_out)
        except Exception as e:
            _ui_proc = None
            _log(f"[UI] Launch error: {e} — retrying in {backoff}s.", tee_out)
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

    # Start Next.js UI server as a daemon thread — auto-restarts on crash
    ui_thread = threading.Thread(
        target=_run_ui, args=(tee_out,), daemon=True
    )
    ui_thread.start()

    cmd = [uv, "run", "python", "-u", "-m", "src.application.gateway.discord_gateway"]
    crashes = 0
    current_proc = None

    def _handle_sigterm(signum, frame):
        """Kill the child and exit cleanly when systemd stops the service."""
        for proc, label in [
            (_dashboard_proc, "DASHBOARD"),
            (_ui_proc, "UI"),
        ]:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
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
