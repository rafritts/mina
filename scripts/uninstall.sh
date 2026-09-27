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

rm -f "$BIN_DIR/$APP_NAME"
rm -rf "$CONFIG_DIR"

echo "Done. mina has been uninstalled."
