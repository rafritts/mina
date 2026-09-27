#!/usr/bin/env bash
# Standalone uninstall — does not depend on the mina CLI being functional.
# If the CLI works, prefer: mina uninstall --yes
set -euo pipefail

APP_NAME="mina"
LABEL="com.rafritts.mina"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/$APP_NAME"
OS="$(uname -s)"

echo "This will stop Mina, remove the service file, and uninstall the CLI."
read -r -p "Type 'yes' to continue: " confirm
[[ "$confirm" != "yes" ]] && echo "Aborted." && exit 0

echo "Uninstalling mina..."

# Same lifecycle as `mina stop`: Ollama is not a separate Keep service.
_stop_ollama() {
  local brew="" c pid
  for c in /opt/homebrew/bin/brew /home/linuxbrew/.linuxbrew/bin/brew /usr/local/bin/brew; do
    if [[ -x "$c" ]]; then
      brew="$c"
      break
    fi
  done
  if [[ -z "$brew" ]] && command -v brew >/dev/null 2>&1; then
    brew="$(command -v brew)"
  fi
  if [[ -n "$brew" ]] && "$brew" list --formula ollama &>/dev/null; then
    echo "Stopping Ollama (brew services)..."
    "$brew" services stop ollama || echo "WARNING: brew services stop ollama failed." >&2
    return 0
  fi
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl --user cat ollama.service &>/dev/null; then
      systemctl --user stop ollama || echo "WARNING: systemctl --user stop ollama failed." >&2
      return 0
    fi
    if systemctl cat ollama.service &>/dev/null; then
      systemctl stop ollama || echo "WARNING: systemctl stop ollama failed." >&2
      return 0
    fi
  fi
  if [[ -f "$CONFIG_DIR/ollama.pid" ]]; then
    pid="$(cat "$CONFIG_DIR/ollama.pid" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "Stopping Ollama (pid ${pid})..."
      kill "$pid" 2>/dev/null || true
    fi
  fi
}
if [[ "$OS" == "Darwin" ]]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  launchctl disable "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
  echo "Removed LaunchAgent (if present)."
else
  systemctl --user stop "$APP_NAME" 2>/dev/null || true
  systemctl --user disable "$APP_NAME" 2>/dev/null || true
  unit="$HOME/.config/systemd/user/$APP_NAME.service"
  if [[ -f "$unit" ]]; then
    rm -f "$unit"
    systemctl --user daemon-reload
    echo "Removed: $unit"
  fi
fi

_stop_ollama || true

rm -f "$BIN_DIR/$APP_NAME"
rm -rf "$CONFIG_DIR"

echo "Done. mina has been uninstalled."
