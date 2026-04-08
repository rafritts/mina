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

`discord_gateway.py` becomes the primary entry point:

```bash
python discord_gateway.py
```

The CLI (`main.py`) still works for development and testing. The heartbeat asyncio background task is started inside `on_ready`.

---

## What This Does Not Cover

- Multi-server support (single-instance bot, one server)
- Voice channels
- Reaction-based interactions
- Content moderation or role-gating
- Dynamic presence reflecting biological state (future)
