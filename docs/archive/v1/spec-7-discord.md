# Spec 7 — Discord Gateway

> Discord is Mina's primary interface. The CLI (`main.py`) becomes a development tool. Everything the user says to her goes through Discord.

---

## Overview

Mina runs as a Discord bot. The gateway layer handles message delivery in and out. The chat loop and heartbeat remain unchanged — the gateway is an adapter that sits in front of them, not a replacement.

**Library:** `discord.py` (same as raika)

---

## Architecture

```
Discord Events
      │
      ▼
discord_gateway.py          ← Event handlers, debouncing, inflight cancellation, typing indicator
      │
      ▼
mina_turn() / heartbeat     ← Unchanged — subconscious + Mina turn
      │
      ▼
discord_gateway.py          ← Chunked text delivery + image attachment delivery
```

The gateway does not know about biology, memory, or the subconscious. It knows how to receive messages and send replies. The chat loop does not know about Discord. Separation is clean.

---

## Configuration

**Environment variables (`.env`):**
```
DISCORD_BOT_TOKEN="..."
XAI_API_KEY="..."
```

**`config.json` additions:**
```json
{
  "discord_channel_allowlist": [],
  "discord_enable_dms": true,
  "discord_default_channel_id": null
}
```

- `discord_channel_allowlist`: List of channel names (e.g. `["#mina"]`). Empty = all channels Mina can see.
- `discord_enable_dms`: Whether Mina responds to DMs.
- `discord_default_channel_id`: Channel ID for startup notifications if needed.

---

## Message Flow — Inbound

### Event: `on_message`

1. Ignore messages from Mina herself
2. Ignore other bots
3. If allowlist is set, ignore channels not on the list
4. If DMs are disabled, ignore DMs
5. Append message to per-channel pending queue
6. Cancel existing debounce task for this channel; start a new one (100ms delay)
7. When debounce fires: cancel any inflight turn for this channel, drain pending queue, call `_run_turn(channel, messages)`

### `_run_turn(channel, messages)`

1. Store the asyncio Task in `_inflight[channel_id]`
2. Show typing indicator (`async with channel.typing()`)
3. Format pending messages as user input — if multiple were batched, join them with newlines
4. Touch `.last_user_active`
5. Call the Mina turn (load state → subconscious → Mina → tools)
6. Deliver response
7. Remove from `_inflight` on completion or cancellation

### Inflight Cancellation

Per-channel task tracking:

```python
_inflight: dict[int, asyncio.Task] = {}
```

When a new message arrives for a channel that already has an inflight turn:
- The running task is cancelled
- The new message is appended to the pending queue
- Debounce fires normally — the new turn picks up all pending messages including those from the cancelled turn

This is simple. No rescue mechanism, no re-prepending. The cancelled turn is just dropped. Mina's state may have been partially updated if tools fired before cancellation — that's acceptable.

---

## History Seeding on Startup

On `on_ready`, for each channel Mina can see (subject to allowlist):

1. Fetch the last N messages from Discord's message history (`N = 50`, configurable)
2. Filter out messages from other bots
3. Format and append to `conversation.json` as if they had been received in real-time
4. Mark a `[DISCORD_SEED]` system message in history so the subconscious knows these are catchup messages

This is the key behavior: if the user sends Mina three messages while she's offline, when the bot comes back up she sees them all and can respond. She was just away — not absent.

**Format:**
```json
{"role": "system", "content": "[DISCORD_SEED]"},
{"role": "user", "content": "username: hey are you there"},
{"role": "user", "content": "username: hello??"},
{"role": "user", "content": "username: ok guess you're asleep"}
```

The bot then immediately runs a turn so Mina can respond to the backlog.

**Deduplication:** Messages already present in `conversation.json` (matched by content + approximate timestamp) are not re-added. This prevents double-seeding on rapid restarts.

---

## Message Flow — Outbound

### Text responses

Discord's hard limit is 2000 characters per message.

**Chunking strategy:** Split on sentence boundaries (`. `, `! `, `? `) at ≤1950 chars. Never cut mid-word or mid-sentence. Send chunks sequentially with a brief delay between them (100–200ms) — simulates natural pacing and avoids rate limiting.

### Image delivery

When Mina calls `generate_image`, the tool returns a file path. The gateway detects `.png` paths in tool results and delivers them as Discord attachments:

```python
await channel.send(file=discord.File(path))
```

If Mina includes text in her response after a `generate_image` call, it is sent as a preceding text message before the attachment.

No embed. Attachment only.

---

## Slash Commands

All commands respond ephemerally unless noted. Built and registered on `on_ready`.

### Session / History

| Command | Description |
|---|---|
| `/new` | Clear `conversation.json` for this session. Fresh start. Mina won't remember anything before this. |
| `/history <n>` | Show the last N entries from conversation history. Default 10. Ephemeral. |

### State / Biology

| Command | Description |
|---|---|
| `/state` | Show Mina's full biological state — first, second, and third-order values. Ephemeral. |
| `/compress <factor>` | Set `time_compression_factor` in config.json. e.g. `/compress 10` for 10x speed. Ephemeral. |

### Sleep

| Command | Description |
|---|---|
| `/sleep <hours>` | Put Mina to sleep for N hours. Writes directly to state.json. |
| `/wake` | Force-wake Mina. Applies a cortisol spike + norepinephrine bump to simulate groggy waking. |

### Heartbeat

| Command | Description |
|---|---|
| `/heartbeat` | Manually trigger one heartbeat cycle (both phases). Useful for testing. Ephemeral. |

### Process Control

| Command | Description |
|---|---|
| `/cancel` | Cancel the current debounce task and/or inflight turn in this channel. Ephemeral. |
| `/cancel-all` | Cancel all inflight turns across all channels. Ephemeral. |
| `/stop` | Create `run/.stopped` flag and exit cleanly. Supervisor will not restart until `mina unstop` is run from the CLI. |
| `/restart` | Exit with code 42. Supervisor restarts immediately with no backoff. |
| `/reset` | Delete bot messages in this channel, clear `conversation.json`, restart (exit 42). |

### Maintenance

| Command | Description |
|---|---|
| `/clean <n>` | Delete the last N messages Mina sent in this channel. Default 10. |
| `/status` | Show uptime, current biological summary (one line), sleeping status, heartbeat interval. Ephemeral. |

---

## Conversation History Format

**Message format in history:**
```json
{"role": "user", "content": "username: message text"}
{"role": "assistant", "content": "response text"}
```

The username prefix in user messages gives Mina context for who is speaking — important if multiple people are in the same channel.

---

## Presence

On startup and after each turn, Mina's Discord presence reflects her sleep state:

- Awake: `online`
- Sleeping: `idle`

No status text that reveals biological values. That breaks the emergent quality.

---

## Entry Point

`discord_gateway.py` is the primary entry point, but it is not run directly. It is started by `supervisor.py`, which is what systemd runs.

The CLI (`main.py`) still works for development and testing without Discord.

---

## Supervisor

`supervisor.py` is a thin process manager that owns the lifecycle of `discord_gateway.py`.

**Restart logic:**
- **Exit code 42** → intentional restart (from `/restart` or `/reset`). No backoff. Restarts immediately.
- **Any other non-zero exit** → crash. Exponential backoff: `2^n` seconds, capped at 60s.
- **Exit code 0 with `run/.stopped` flag present** → maintenance stop. Supervisor does NOT restart. Waits for flag removal.

**Stop flow (`/stop` command):**
1. Discord command creates `run/.stopped` and calls `os._exit(0)`
2. Supervisor sees exit code 0 + flag exists → does not restart
3. `mina unstop` (CLI) removes the flag
4. `mina start` or systemd restart brings it back up

**Restart flow (`/restart` command):**
1. Discord command calls `os._exit(42)`
2. Supervisor sees exit code 42 → restarts immediately, no backoff

---

## CLI — `mina` Command

A bash script installed at `~/.local/bin/mina` (symlinked from `scripts/mina`). Modeled directly on raika's `scripts/raika`.

```
Setup:
  install          Generate service file, enable autostart, start
  uninstall        Stop, remove service file and CLI symlink
  setup            Regenerate service file (after repo moves or uv path changes)

Service:
  start            Start the mina service
  stop             Stop the mina service
  restart          Restart the mina service
  status           Show systemd service status
  enable           Enable autostart on boot
  disable          Disable autostart on boot
  logs [-f] [-n N] Show logs (default 100 lines; -f to follow)

Maintenance:
  update           git pull, uv sync, restart
  unstop           Remove run/.stopped flag (re-enables supervisor restart)
  clean [--yes]    Clear runtime data: conversation.json, state.json, memory/rag/
```

---

## Systemd Service

User-level service (not system-wide). Generated by `scripts/install.sh` and written to `~/.config/systemd/user/mina.service`.

```ini
[Unit]
Description=Mina Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/home/restlessapi/workspace/mina
EnvironmentFile=/home/restlessapi/workspace/mina/.env
ExecStart=/home/restlessapi/.local/bin/uv run python supervisor.py
Restart=on-failure
RestartSec=5
KillMode=process
Environment="HOME=/home/restlessapi"
Environment="PATH=/home/restlessapi/.local/bin:/usr/local/bin:/usr/bin:/bin"

[Install]
WantedBy=default.target
```

Key points:
- `EnvironmentFile` loads `.env` (Discord token, xAI API key)
- `ExecStart` runs `supervisor.py`, not `discord_gateway.py` directly
- `Restart=on-failure` — systemd handles crash recovery at the outer level; the supervisor handles it at the inner level
- `KillMode=process` — SIGTERM goes to supervisor only; supervisor propagates to gateway

---

## Runtime Directory

```
run/
  .stopped          — exists when /stop was issued; prevents supervisor restart
  ready             — written when gateway is fully initialized (CLI uses to detect startup)
```

---

## Install Script

`scripts/install.sh`:
1. Verify `uv` is present
2. Run `uv sync` to install deps
3. Write `~/.config/raika/dir` → repo path
4. Symlink `~/.local/bin/mina` → `scripts/mina`
5. Generate `~/.config/systemd/user/mina.service` with dynamic path substitution
6. `systemctl --user daemon-reload && systemctl --user enable mina`
7. Warn if `.env` is missing

---

## What This Does Not Cover

- Multi-server support (single-instance bot, one server)
- Voice channels
- Reaction-based interactions
- Content moderation or role-gating
- Dynamic presence reflecting biological state (future)
- macOS launchd support (Linux/systemd only for now)
