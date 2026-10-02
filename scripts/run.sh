#!/usr/bin/env bash
# Service entrypoint. Exec'd by systemd or launchd, not by a login shell.
# PATH arrives already set. Do not prepend dirname of APP_UV_BIN or APP_NPM_BIN:
# those values may be symlinks, and dirname does not follow the link.
#
# Mina is two processes in this group: Python backend on MINA_BACKEND_PORT
# (5100) and Next UI on APP_PORT (2050). APP_* and MINA_* are aliases for the
# same binaries; the UI port is APP_PORT, also exported as MINA_UI_PORT.
set -euo pipefail

APP_NAME="mina"
DEFAULT_PORT="2050"
BACKEND_DEFAULT="5100"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

TOOLS="$HOME/.config/$APP_NAME/tools.env"
if [[ -f "$TOOLS" ]]; then
  # shellcheck disable=SC1090
  source "$TOOLS"
fi

# The service PATH wins. .env is app config and must not replace it, nor the
# ports and tool binaries the unit / tools.env already set (the CLI waits on
# those). Values that were empty can still come from .env.
_saved_app_port="${APP_PORT:-}"
_saved_mina_ui="${MINA_UI_PORT:-}"
_saved_backend="${MINA_BACKEND_PORT:-}"
_saved_app_uv="${APP_UV_BIN:-}"
_saved_mina_uv="${MINA_UV_BIN:-}"
_saved_app_npm="${APP_NPM_BIN:-}"
_saved_mina_npm="${MINA_NPM_BIN:-}"
_service_path="$PATH"
if [[ -f "$REPO_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_DIR/.env"
  set +a
fi
PATH="$_service_path"
export PATH
[[ -n "$_saved_app_port" ]] && APP_PORT="$_saved_app_port"
[[ -n "$_saved_mina_ui" ]] && MINA_UI_PORT="$_saved_mina_ui"
[[ -n "$_saved_backend" ]] && MINA_BACKEND_PORT="$_saved_backend"
[[ -n "$_saved_app_uv" ]] && APP_UV_BIN="$_saved_app_uv"
[[ -n "$_saved_mina_uv" ]] && MINA_UV_BIN="$_saved_mina_uv"
[[ -n "$_saved_app_npm" ]] && APP_NPM_BIN="$_saved_app_npm"
[[ -n "$_saved_mina_npm" ]] && MINA_NPM_BIN="$_saved_mina_npm"

# UI port the CLI waits on and that GET /api/build is served from.
# APP_PORT is canonical. MINA_UI_PORT covers a unit written before APP_*.
if [[ -z "${APP_PORT:-}" ]]; then
  APP_PORT="${MINA_UI_PORT:-$DEFAULT_PORT}"
fi
export APP_PORT
export MINA_UI_PORT="$APP_PORT"
export MINA_BACKEND_PORT="${MINA_BACKEND_PORT:-$BACKEND_DEFAULT}"

if [[ -z "${APP_UV_BIN:-}" ]]; then
  APP_UV_BIN="${MINA_UV_BIN:-}"
fi
if [[ -z "${APP_NPM_BIN:-}" ]]; then
  APP_NPM_BIN="${MINA_NPM_BIN:-}"
fi
UV_BIN="${APP_UV_BIN:-uv}"
NPM_BIN="${APP_NPM_BIN:-npm}"
export APP_UV_BIN="$UV_BIN"
export MINA_UV_BIN="$UV_BIN"
export APP_NPM_BIN="$NPM_BIN"
export MINA_NPM_BIN="$NPM_BIN"

export NODE_ENV="${NODE_ENV:-production}"
export MINA_BACKEND_HOST="${MINA_BACKEND_HOST:-127.0.0.1}"
export COMFY_FE_URL="${COMFY_FE_URL:-http://127.0.0.1:8886}"
# ComfyUI on restless-mint. "Mint up" is an HTTP probe of this URL.
# COMFY_FE_URL is the Krea frontend on the Mini (often nothing on :8886).
# Point that frontend's Comfy upstream here — not at a local GPU.
export MINT_COMFY_URL="${MINT_COMFY_URL:-http://restless-mint:8188}"
export COMFY_BASE_URL="${COMFY_BASE_URL:-$MINT_COMFY_URL}"

mkdir -p "$REPO_DIR/run" "$REPO_DIR/logs"
rm -f "$REPO_DIR/run/ready"

# Free ports if orphaned listeners remain (stale HTML / EADDRINUSE).
_free_port() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    if fuser "${port}/tcp" >/dev/null 2>&1; then
      echo "run.sh: freeing port ${port} (orphan listener)" >&2
      fuser -k "${port}/tcp" >/dev/null 2>&1 || true
      sleep 0.4
    fi
  elif command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -nP -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      echo "run.sh: freeing port ${port} (orphan listener)" >&2
      # shellcheck disable=SC2086
      kill $pids 2>/dev/null || true
      sleep 0.4
    fi
  elif command -v ss >/dev/null 2>&1; then
    if ss -ltn "sport = :${port}" 2>/dev/null | grep -q LISTEN; then
      echo "run.sh: warning: port ${port} already in use" >&2
    fi
  fi
}

_free_port "$MINA_BACKEND_PORT"
_free_port "$APP_PORT"

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

echo "run.sh: starting backend on :${MINA_BACKEND_PORT}" >&2
"$UV_BIN" run python main.py &
BACKEND_PID=$!

# Wait until health is up (or backend dies).
for ((_i=1; _i<=60; _i++)); do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "run.sh: backend exited early" >&2
    exit 1
  fi
  if curl -sf "http://127.0.0.1:${MINA_BACKEND_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -sf "http://127.0.0.1:${MINA_BACKEND_PORT}/health" >/dev/null 2>&1; then
  echo "run.sh: backend health check failed" >&2
  exit 1
fi

echo "run.sh: starting UI on :${APP_PORT}" >&2
(
  cd "$REPO_DIR/ui"
  # package.json `start` pins host/port 2050; PORT is exported for Next as well.
  export PORT="$APP_PORT"
  exec "$NPM_BIN" run start
) &
UI_PID=$!

for ((_i=1; _i<=90; _i++)); do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "run.sh: backend died while waiting for UI" >&2
    exit 1
  fi
  if ! kill -0 "$UI_PID" 2>/dev/null; then
    echo "run.sh: UI process exited early" >&2
    exit 1
  fi
  if curl -sf "http://127.0.0.1:${APP_PORT}/" >/dev/null 2>&1; then
    touch "$REPO_DIR/run/ready"
    echo "run.sh: ready on :${APP_PORT} (backend :${MINA_BACKEND_PORT})" >&2
    break
  fi
  sleep 0.5
done

if [[ ! -f "$REPO_DIR/run/ready" ]]; then
  echo "run.sh: readiness check failed" >&2
  exit 1
fi

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
