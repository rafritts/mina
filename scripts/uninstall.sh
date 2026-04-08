#!/usr/bin/env bash
# Standalone uninstall — does not depend on the mina CLI being functional.
# If the CLI works, prefer: mina uninstall
set -euo pipefail

BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/mina"
SYSTEMD_DIR="$HOME/.config/systemd/user"
UNIT="mina.service"

echo "This will stop Mina, remove the service file, and uninstall the CLI."
read -r -p "Type 'yes' to continue: " confirm
[[ "$confirm" != "yes" ]] && echo "Aborted." && exit 0

echo "Uninstalling mina..."

systemctl --user stop "$UNIT" 2>/dev/null || true
systemctl --user disable "$UNIT" 2>/dev/null || true

if [[ -f "$SYSTEMD_DIR/$UNIT" ]]; then
    rm -f "$SYSTEMD_DIR/$UNIT"
    systemctl --user daemon-reload
    echo "Removed: $SYSTEMD_DIR/$UNIT"
fi

rm -f "$BIN_DIR/mina"
rm -rf "$CONFIG_DIR"

echo "Done. mina has been uninstalled."
