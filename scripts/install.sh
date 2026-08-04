#!/usr/bin/env bash
# Install Mina as a systemd user service (sim backend + Next UI) and CLI.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETUP_ONLY="${1:-}"

# ---------------------------------------------------------------------------
# Find uv
# ---------------------------------------------------------------------------
UV_BIN=""
for candidate in \
    "$HOME/.local/bin/uv" \
    "$HOME/.cargo/bin/uv" \
    "/home/linuxbrew/.linuxbrew/bin/uv" \
    "$(command -v uv 2>/dev/null || true)"
do
    [[ -x "$candidate" ]] || continue
    UV_BIN="$candidate"
    break
done

if [[ -z "$UV_BIN" ]]; then
    echo "Error: uv not found. Install it from https://github.com/astral-sh/uv" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Find npm / Node
# ---------------------------------------------------------------------------
NODE_BIN_DIR=""
for candidate in \
    "$(command -v npm 2>/dev/null || true)" \
    "$HOME/.nvm/versions/node/"*/bin/npm \
    "/home/linuxbrew/.linuxbrew/bin/npm" \
    "/usr/local/bin/npm" \
    "/usr/bin/npm"
do
    [[ -x "$candidate" ]] || continue
    NODE_BIN_DIR="$(cd "$(dirname "$candidate")" && pwd)"
    break
done

if [[ -z "$NODE_BIN_DIR" ]]; then
    echo "Error: npm/node not found. Install Node.js 20+ first." >&2
    exit 1
fi

NPM_BIN="$NODE_BIN_DIR/npm"
export PATH="$NODE_BIN_DIR:$PATH"

echo "Using uv:  $UV_BIN"
echo "Using npm: $NPM_BIN"
echo "Repo:      $REPO_DIR"

# ---------------------------------------------------------------------------
# Dependencies + UI build
# ---------------------------------------------------------------------------
if [[ "$SETUP_ONLY" != "--setup-only" ]]; then
    echo "Installing Python dependencies..."
    (cd "$REPO_DIR" && "$UV_BIN" sync)

    echo "Installing UI dependencies..."
    (cd "$REPO_DIR/ui" && "$NPM_BIN" install)

    echo "Building UI..."
    (cd "$REPO_DIR/ui" && "$NPM_BIN" run build)
fi

# ---------------------------------------------------------------------------
# Config dir + CLI symlink
# ---------------------------------------------------------------------------
mkdir -p "$HOME/.config/mina" "$HOME/.local/bin"
echo "$REPO_DIR" > "$HOME/.config/mina/dir"
ln -sf "$REPO_DIR/scripts/mina" "$HOME/.local/bin/mina"
chmod +x "$REPO_DIR/scripts/mina" "$REPO_DIR/scripts/run.sh" "$REPO_DIR/scripts/install.sh"
echo "CLI installed: ~/.local/bin/mina"

# ---------------------------------------------------------------------------
# Systemd user unit
# ---------------------------------------------------------------------------
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/mina.service"
mkdir -p "$SERVICE_DIR"

# PATH must include node + uv for the run script.
SERVICE_PATH="$NODE_BIN_DIR:$(dirname "$UV_BIN"):$HOME/.local/bin:/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Mina chat + neurosim (Next UI + Python backend)
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$REPO_DIR
EnvironmentFile=-$REPO_DIR/.env
Environment=HOME=$HOME
Environment=PATH=$SERVICE_PATH
Environment=NODE_ENV=production
Environment=MINA_UV_BIN=$UV_BIN
Environment=MINA_NPM_BIN=$NPM_BIN
Environment=MINA_BACKEND_PORT=5100
Environment=MINA_UI_PORT=2050
Environment=COMFY_FE_URL=http://127.0.0.1:8886
ExecStart=$REPO_DIR/scripts/run.sh
Restart=on-failure
RestartSec=5
KillMode=control-group

[Install]
WantedBy=default.target
EOF

echo "Service file written: $SERVICE_FILE"
systemctl --user daemon-reload

# ---------------------------------------------------------------------------
# Enable and start
# ---------------------------------------------------------------------------
if [[ "$SETUP_ONLY" != "--setup-only" ]]; then
    systemctl --user enable mina
    echo "Autostart enabled."

    if ! command -v grok >/dev/null 2>&1 && [[ ! -x "$HOME/.grok/bin/grok" ]]; then
        echo ""
        echo "WARNING: Grok Build CLI not found (expected grok on PATH or ~/.grok/bin/grok)."
        echo "Install/login with Grok Build, then: mina start"
        echo ""
    fi
    if [[ ! -f "$REPO_DIR/.env" ]]; then
        echo ""
        echo "Note: $REPO_DIR/.env not found (optional)."
        echo "Chat uses headless grok CLI auth — no XAI_API_KEY required for turns."
        echo "Optional: XAI_API_KEY only if FREETIME web/x search should use the API."
        echo ""
        echo "Then run: mina start"
    else
        systemctl --user restart mina
        echo -n "Starting"
        for _ in $(seq 1 90); do
            sleep 1
            echo -n "."
            if [[ -f "$REPO_DIR/run/ready" ]] || curl -sf http://localhost:2050/ &>/dev/null; then
                echo " ready."
                break
            fi
        done
        echo ""
        echo "UI:      http://localhost:2050"
        echo "Backend: http://localhost:5100"
        if curl -sf http://localhost:2050/api/build &>/dev/null; then
            echo -n "Build:   "
            curl -s http://localhost:2050/api/build
            echo ""
        fi
    fi
fi

# ---------------------------------------------------------------------------
# PATH reminder
# ---------------------------------------------------------------------------
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ""
    echo "NOTE: ~/.local/bin is not in your PATH."
    echo "Add to ~/.zshrc or ~/.bashrc:"
    echo '  export PATH="$HOME/.local/bin:$PATH"'
fi

echo "Done. Run 'mina help' for usage."
