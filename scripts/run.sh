#!/usr/bin/env bash
# Start Mina: Python sim backend (:5100) + Next UI (:2050).
# Used as systemd ExecStart. Both children die with this process group.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

UV_BIN="${MINA_UV_BIN:-uv}"
NPM_BIN="${MINA_NPM_BIN:-npm}"
BACKEND_PORT="${MINA_BACKEND_PORT:-5100}"
UI_PORT="${MINA_UI_PORT:-2050}"

if [[ -f "$REPO_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_DIR/.env"
  set +a
fi

export NODE_ENV="${NODE_ENV:-production}"
export MINA_BACKEND_HOST="${MINA_BACKEND_HOST:-127.0.0.1}"
export MINA_BACKEND_PORT="$BACKEND_PORT"
export PATH="$(dirname "$UV_BIN" 2>/dev/null || true):$HOME/.local/bin:/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin${PATH:+:$PATH}"

# Free ports if orphaned listeners remain (stale HTML / EADDRINUSE).
_free_port() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    if fuser "${port}/tcp" >/dev/null 2>&1; then
      echo "run.sh: freeing port ${port} (orphan listener)" >&2
      fuser -k "${port}/tcp" >/dev/null 2>&1 || true
      sleep 0.4
    fi
  elif command -v ss >/dev/null 2>&1; then
    if ss -ltn "sport = :${port}" 2>/dev/null | grep -q LISTEN; then
      echo "run.sh: warning: port ${port} already in use" >&2
    fi
  fi
}

_free_port "$BACKEND_PORT"
_free_port "$UI_PORT"

rm -f "$REPO_DIR/run/ready"
mkdir -p "$REPO_DIR/run" "$REPO_DIR/logs"

BACKEND_PID=""
UI_PID=""

_cleanup() {
  local code=$?
  rm -f "$REPO_DIR/run/ready"
  if [[ -n "$UI_PID" ]] && kill -0 "$UI_PID" 2>/dev/null; then
    kill "$UI_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
  exit "$code"
}
trap _cleanup EXIT INT TERM

echo "run.sh: starting backend on :${BACKEND_PORT}" >&2
"$UV_BIN" run python main.py &
BACKEND_PID=$!

# Wait until health is up (or backend dies).
for _ in $(seq 1 60); do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "run.sh: backend exited early" >&2
    exit 1
  fi
  if curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1; then
  echo "run.sh: backend health check failed" >&2
  exit 1
fi

echo "run.sh: starting UI on :${UI_PORT}" >&2
(
  cd "$REPO_DIR/ui"
  # package.json `start` pins host/port; PORT env is also honored by Next.
  export PORT="$UI_PORT"
  exec "$NPM_BIN" run start
) &
UI_PID=$!

# Mark ready when UI answers (or after a short grace if curl slow).
for _ in $(seq 1 90); do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "run.sh: backend died while waiting for UI" >&2
    exit 1
  fi
  if ! kill -0 "$UI_PID" 2>/dev/null; then
    echo "run.sh: UI process exited early" >&2
    exit 1
  fi
  if curl -sf "http://127.0.0.1:${UI_PORT}/" >/dev/null 2>&1; then
    touch "$REPO_DIR/run/ready"
    echo "run.sh: ready (UI :${UI_PORT}, backend :${BACKEND_PORT})" >&2
    break
  fi
  sleep 0.5
done

# Stay alive while both children run; exit if either dies.
while true; do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "run.sh: backend exited" >&2
    exit 1
  fi
  if ! kill -0 "$UI_PID" 2>/dev/null; then
    echo "run.sh: UI exited" >&2
    exit 1
  fi
  sleep 2
done
