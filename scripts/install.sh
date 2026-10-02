#!/usr/bin/env bash
# Install mina as a user service and a ~/.local/bin command.
# Linux: systemd --user. macOS: launchd LaunchAgent. Same command either way.
#
# Dual process (scripts/run.sh): UI on APP_PORT / MINA_UI_PORT 2050,
# Python backend on MINA_BACKEND_PORT 5100. Both names are written into the
# unit or plist and into ~/.config/mina/tools.env.
set -euo pipefail

APP_NAME="mina"
LABEL="com.rafritts.mina"
DEFAULT_PORT="2050"
BACKEND_PORT="5100"
COMFY_FE_URL_DEFAULT="http://127.0.0.1:8886"
MINT_COMFY_URL_DEFAULT="http://restless-mint:8188"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETUP_ONLY="${1:-}"
OS="$(uname -s)"

# Directory that should lead PATH for this executable.
# Walk symlinks. Stop at the first directory that contains `node`.
# dirname(symlink) is the symlink's folder. realpath lands in a Cellar keg.
# Neither of those is the right prefix when `node` sits one hop earlier.
bin_dir_for_path() {
  local bin="$1" dir next
  [[ -e "$bin" || -L "$bin" ]] || return 1
  while [[ -L "$bin" ]]; do
    dir="$(cd "$(dirname "$bin")" && pwd -P)"
    if [[ -x "$dir/node" ]]; then
      printf '%s\n' "$dir"
      return 0
    fi
    next="$(readlink "$bin")"
    if [[ "$next" != /* ]]; then
      next="$dir/$next"
    fi
    bin="$(cd "$(dirname "$next")" && pwd -P)/$(basename "$next")"
  done
  dir="$(cd "$(dirname "$bin")" && pwd -P)"
  printf '%s\n' "$dir"
}

add_path() {
  local dir="$1"
  [[ -n "$dir" && -d "$dir" ]] || return 0
  case ":${SERVICE_PATH:-}:" in
    *":$dir:"*) ;;
    *) SERVICE_PATH="${SERVICE_PATH:+$SERVICE_PATH:}$dir" ;;
  esac
}

brew_prefix() {
  local c
  for c in /opt/homebrew/bin/brew /home/linuxbrew/.linuxbrew/bin/brew /usr/local/bin/brew; do
    if [[ -x "$c" ]]; then
      "$c" --prefix
      return 0
    fi
  done
  if command -v brew >/dev/null 2>&1; then
    brew --prefix
    return 0
  fi
  return 1
}

latest_nvm_npm() {
  python3 -c '
import pathlib
root = pathlib.Path.home() / ".nvm" / "versions" / "node"
if not root.is_dir():
    raise SystemExit(0)
def key(p):
    nums = []
    for piece in p.parent.parent.name.lstrip("v").split("."):
        nums.append(int(piece) if piece.isdigit() else 0)
    return nums
bins = [p for p in root.glob("*/bin/npm") if p.exists()]
if not bins:
    raise SystemExit(0)
print(sorted(bins, key=key)[-1])
'
}

first_executable() {
  local c
  for c in "$@"; do
    [[ -n "$c" && -x "$c" ]] || continue
    printf '%s\n' "$c"
    return 0
  done
  return 1
}

xml_escape() {
  python3 -c 'import sys
s = sys.argv[1]
for a, b in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ("\"", "&quot;")):
    s = s.replace(a, b)
sys.stdout.write(s)' "$1"
}

write_tools_env() {
  mkdir -p "$HOME/.config/$APP_NAME"
  cat > "$HOME/.config/$APP_NAME/tools.env" <<EOF
APP_UV_BIN=${UV_BIN:-}
APP_NPM_BIN=${NPM_BIN:-}
APP_PORT=${DEFAULT_PORT}
MINA_UV_BIN=${UV_BIN:-}
MINA_NPM_BIN=${NPM_BIN:-}
MINA_BACKEND_PORT=${BACKEND_PORT}
MINA_UI_PORT=${DEFAULT_PORT}
PATH=${SERVICE_PATH}
EOF
  printf '%s\n' "$REPO_DIR" > "$HOME/.config/$APP_NAME/dir"
}

write_systemd_unit() {
  local unit_dir="$HOME/.config/systemd/user"
  mkdir -p "$unit_dir"
  cat > "$unit_dir/$APP_NAME.service" <<EOF
[Unit]
Description=${APP_NAME}
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=${REPO_DIR}
Environment=HOME=${HOME}
Environment=PATH=${SERVICE_PATH}
Environment=APP_UV_BIN=${UV_BIN:-}
Environment=APP_NPM_BIN=${NPM_BIN:-}
Environment=APP_PORT=${DEFAULT_PORT}
Environment=MINA_UV_BIN=${UV_BIN:-}
Environment=MINA_NPM_BIN=${NPM_BIN:-}
Environment=MINA_BACKEND_PORT=${BACKEND_PORT}
Environment=MINA_UI_PORT=${DEFAULT_PORT}
Environment=COMFY_FE_URL=${COMFY_FE_URL_DEFAULT}
Environment=MINT_COMFY_URL=${MINT_COMFY_URL_DEFAULT}
Environment=COMFY_BASE_URL=${MINT_COMFY_URL_DEFAULT}
Environment=NODE_ENV=production
ExecStart=${REPO_DIR}/scripts/run.sh
Restart=on-failure
RestartSec=5
KillMode=control-group

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  echo "Service file written: $unit_dir/$APP_NAME.service"
}

write_launch_agent() {
  local agent_dir="$HOME/Library/LaunchAgents"
  local log_dir="$HOME/Library/Logs"
  local plist="$agent_dir/$LABEL.plist"
  mkdir -p "$agent_dir" "$log_dir"
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$(xml_escape "$LABEL")</string>
  <key>WorkingDirectory</key>
  <string>$(xml_escape "$REPO_DIR")</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$(xml_escape "$REPO_DIR/scripts/run.sh")</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>$(xml_escape "$HOME")</string>
    <key>PATH</key>
    <string>$(xml_escape "$SERVICE_PATH")</string>
    <key>APP_UV_BIN</key>
    <string>$(xml_escape "${UV_BIN:-}")</string>
    <key>APP_NPM_BIN</key>
    <string>$(xml_escape "${NPM_BIN:-}")</string>
    <key>APP_PORT</key>
    <string>${DEFAULT_PORT}</string>
    <key>MINA_UV_BIN</key>
    <string>$(xml_escape "${UV_BIN:-}")</string>
    <key>MINA_NPM_BIN</key>
    <string>$(xml_escape "${NPM_BIN:-}")</string>
    <key>MINA_BACKEND_PORT</key>
    <string>${BACKEND_PORT}</string>
    <key>MINA_UI_PORT</key>
    <string>${DEFAULT_PORT}</string>
    <key>COMFY_FE_URL</key>
    <string>$(xml_escape "$COMFY_FE_URL_DEFAULT")</string>
    <key>MINT_COMFY_URL</key>
    <string>$(xml_escape "$MINT_COMFY_URL_DEFAULT")</string>
    <key>COMFY_BASE_URL</key>
    <string>$(xml_escape "$MINT_COMFY_URL_DEFAULT")</string>
    <key>NODE_ENV</key>
    <string>production</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key>
    <false/>
  </dict>
  <key>AbandonProcessGroup</key>
  <false/>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>$(xml_escape "$log_dir/$APP_NAME.log")</string>
  <key>StandardErrorPath</key>
  <string>$(xml_escape "$log_dir/$APP_NAME.log")</string>
</dict>
</plist>
EOF
  echo "LaunchAgent written: $plist"
  echo "A loaded agent keeps its old plist until: mina restart"
}

install_cli() {
  mkdir -p "$HOME/.local/bin" "$REPO_DIR/run"
  chmod +x "$REPO_DIR/scripts/$APP_NAME" "$REPO_DIR/scripts/run.sh" "$REPO_DIR/scripts/install.sh"
  ln -sfn "$REPO_DIR/scripts/$APP_NAME" "$HOME/.local/bin/$APP_NAME"
  echo "CLI installed: ~/.local/bin/$APP_NAME"
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *)
      echo "Add ~/.local/bin to PATH in the shell rc:"
      echo '  export PATH="$HOME/.local/bin:$PATH"'
      ;;
  esac
}

main() {
  local prefix="" nvm_npm=""
  prefix="$(brew_prefix || true)"
  nvm_npm="$(latest_nvm_npm || true)"

  UV_BIN="$(first_executable \
    "$HOME/.local/bin/uv" \
    "$HOME/.cargo/bin/uv" \
    "${prefix:+$prefix/bin/uv}" \
    "$(command -v uv 2>/dev/null || true)" \
    || true)"

  NPM_BIN="$(first_executable \
    "$(command -v npm 2>/dev/null || true)" \
    "$nvm_npm" \
    "${prefix:+$prefix/bin/npm}" \
    /usr/local/bin/npm \
    /usr/bin/npm \
    || true)"

  NODE_DIR=""
  if [[ -n "${NPM_BIN:-}" ]]; then
    NODE_DIR="$(bin_dir_for_path "$NPM_BIN")"
  fi

  # Create this before PATH assembly so a fresh home still records it.
  # add_path skips directories that do not exist yet.
  mkdir -p "$HOME/.local/bin"

  SERVICE_PATH=""
  add_path "$NODE_DIR"
  add_path "${prefix:+$prefix/bin}"
  add_path "$HOME/.local/bin"
  add_path /usr/local/bin
  add_path /usr/bin
  add_path /bin
  if [[ "$OS" == "Darwin" ]]; then
    add_path /usr/sbin
    add_path /sbin
  fi

  echo "Repo:  $REPO_DIR"
  echo "uv:    ${UV_BIN:-<none>}"
  echo "npm:   ${NPM_BIN:-<none>}"
  echo "PATH:  $SERVICE_PATH"
  echo "UI:    ${DEFAULT_PORT}    Backend: ${BACKEND_PORT}"

  if [[ "$SETUP_ONLY" != "--setup-only" ]]; then
    if [[ -n "${UV_BIN:-}" && -f "$REPO_DIR/pyproject.toml" ]]; then
      (cd "$REPO_DIR" && "$UV_BIN" sync)
    fi
    if [[ -n "${NPM_BIN:-}" && -f "$REPO_DIR/ui/package.json" ]]; then
      (cd "$REPO_DIR/ui" && "$NPM_BIN" install && "$NPM_BIN" run build)
    elif [[ -n "${NPM_BIN:-}" && -f "$REPO_DIR/package.json" ]]; then
      (cd "$REPO_DIR" && "$NPM_BIN" install && "$NPM_BIN" run build)
    fi
  fi

  install_cli
  write_tools_env
  if [[ "$OS" == "Darwin" ]]; then
    write_launch_agent
  else
    write_systemd_unit
  fi

  if [[ "$SETUP_ONLY" != "--setup-only" ]]; then
    if [[ ! -f "$REPO_DIR/.env" ]]; then
      echo "Note: $REPO_DIR/.env not found (optional)."
      echo "Chat uses headless grok CLI auth — no XAI_API_KEY required for turns."
    fi
    if ! command -v grok >/dev/null 2>&1 && [[ ! -x "$HOME/.grok/bin/grok" ]]; then
      echo "WARNING: Grok Build CLI not found (expected grok on PATH or ~/.grok/bin/grok)."
      echo "Install/login with Grok Build before chatting."
    fi
    if [[ "$OS" == "Darwin" ]]; then
      /bin/launchctl enable "gui/$(id -u)/$LABEL" || true
    else
      systemctl --user enable "$APP_NAME"
    fi
    echo "Autostart enabled."
    "$HOME/.local/bin/$APP_NAME" start
  fi

  echo "Done. Run '$APP_NAME help' for usage."
}

main "$@"
