#!/usr/bin/env bash
# Install Mina as a systemd user service and create the 'mina' CLI command.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETUP_ONLY="${1:-}"

# ---------------------------------------------------------------------------
# Find uv
# ---------------------------------------------------------------------------
UV_BIN=""
for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" "$(command -v uv 2>/dev/null)"; do
    if [[ -x "$candidate" ]]; then
        UV_BIN="$candidate"
        break
    fi
done

if [[ -z "$UV_BIN" ]]; then
    echo "Error: uv not found. Install it from https://github.com/astral-sh/uv" >&2
    exit 1
fi

echo "Using uv: $UV_BIN"
echo "Repo:     $REPO_DIR"

# ---------------------------------------------------------------------------
# Install Python dependencies
# ---------------------------------------------------------------------------
if [[ "$SETUP_ONLY" != "--setup-only" ]]; then
    echo "Installing dependencies..."
    (cd "$REPO_DIR" && "$UV_BIN" sync)
fi

# ---------------------------------------------------------------------------
# Store repo path for the CLI
# ---------------------------------------------------------------------------
mkdir -p "$HOME/.config/mina"
echo "$REPO_DIR" > "$HOME/.config/mina/dir"

# ---------------------------------------------------------------------------
# Install CLI symlink
# ---------------------------------------------------------------------------
mkdir -p "$HOME/.local/bin"
ln -sf "$REPO_DIR/scripts/mina" "$HOME/.local/bin/mina"
chmod +x "$REPO_DIR/scripts/mina"
echo "CLI installed: ~/.local/bin/mina"

# ---------------------------------------------------------------------------
# Generate systemd user service
# ---------------------------------------------------------------------------
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/mina.service"
mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Mina Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$REPO_DIR
EnvironmentFile=$REPO_DIR/.env
ExecStart=$UV_BIN run python supervisor.py
Restart=on-failure
RestartSec=5
KillMode=process
Environment="HOME=$HOME"
Environment="PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

[Install]
WantedBy=default.target
EOF

echo "Service file written: $SERVICE_FILE"
systemctl --user daemon-reload

# ---------------------------------------------------------------------------
# Enable and start (unless setup-only)
# ---------------------------------------------------------------------------
if [[ "$SETUP_ONLY" != "--setup-only" ]]; then
    systemctl --user enable mina
    echo "Autostart enabled."

    if [[ ! -f "$REPO_DIR/.env" ]]; then
        echo ""
        echo "WARNING: $REPO_DIR/.env not found."
        echo "Create it with at minimum:"
        echo "  DISCORD_BOT_TOKEN=your-token-here"
        echo "  XAI_API_KEY=your-key-here"
        echo ""
        echo "Then run: mina start"
    else
        systemctl --user start mina
        echo -n "Starting"
        for i in $(seq 1 30); do
            sleep 1
            echo -n "."
            if [[ -f "$REPO_DIR/run/ready" ]]; then
                echo " ready."
                break
            fi
        done
        echo ""
    fi
fi

# ---------------------------------------------------------------------------
# PATH reminder
# ---------------------------------------------------------------------------
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    echo ""
    echo "NOTE: ~/.local/bin is not in your PATH."
    echo "Add to ~/.zshrc or ~/.bashrc:"
    echo '  export PATH="$HOME/.local/bin:$PATH"'
fi

echo "Done. Run 'mina help' for usage."
