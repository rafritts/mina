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
discord_gateway.py          ← Event handlers, debouncing, typing indicator
      │
      ▼
main.py (chat loop)         ← Unchanged — subconscious + Mina turn
      │
      ▼
discord_gateway.py          ← Delivers response back to Discord
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
2. Ignore bots
3. If allowlist is set, ignore channels not on the list
4. If DMs are disabled, ignore DMs
5. Append message to per-channel pending queue
6. Cancel existing debounce task for this channel; start a new one (100ms delay)
7. When debounce fires: drain pending queue, call `_run_turn(channel, messages)`

### `_run_turn(channel, messages)`

1. Show typing indicator (`async with channel.typing()`)
2. Format messages as user input (join multiple pending messages if batched)
3. Call the main chat loop turn directly (not as a subprocess)
4. Send response back to Discord
5. If Mina is asleep: the subconscious system prompt will reflect that; her response (or non-response) is still delivered

**No inflight cancellation for now.** If Mina is mid-turn when a new message arrives, it queues. Keep it simple until there's a reason to add it.

---

## Message Flow — Outbound

### Text responses

Discord's hard limit is 2000 characters per message. Mina's responses will often exceed this.

**Chunking strategy:** Split on sentence boundaries (`. `, `! `, `? `) at ≤1950 chars. Never cut mid-word or mid-sentence. Send chunks sequentially with a small delay between them (simulates natural pacing, avoids rate limiting).

Unlike raika which raises an error and forces the LLM to retry, Mina's responses are prose-heavy and chunking is the right answer here.

### Image responses

When Mina calls `generate_image`, the result path is returned to her turn. The gateway detects image paths in tool results and delivers them as Discord file attachments.

```python
await channel.send(file=discord.File(path))
```

If Mina includes a caption in her response after calling `generate_image`, it is sent as a preceding text message.

No embed. Attachment only (same as raika).

---

## ComfyUI Delivery Layer

The `generate_image` tool in `tools_mina.py` currently returns a file path. That path needs to be delivered to Discord.

**Pattern:**
- `handle_generate_image()` in `tools_mina.py` returns the path as a string
- The gateway's turn runner checks tool results: if a result looks like a file path ending in `.png`, it delivers it as an attachment
- The gateway holds the channel reference throughout the turn, so delivery target is always resolved

This keeps the tool itself Discord-agnostic. The gateway is what knows how to send files.

---

## Slash Commands

Minimal set for MVP. Add more as needed.

| Command | Description |
|---|---|
| `/new` | Clear conversation history for this channel. Fresh start. |
| `/state` | Show Mina's current biological state (first, second, third-order values). Ephemeral. |
| `/sleep <hours>` | Tell Mina to go to sleep for N hours. |
| `/wake` | Force-wake Mina from sleep. She'll be groggy. |
| `/compress <factor>` | Set time compression factor (e.g. `/compress 10` for 10x). Ephemeral confirmation. |
| `/heartbeat` | Manually trigger one heartbeat cycle. Ephemeral. |

All commands respond ephemerally (visible only to the user who ran them) unless they produce content Mina should also see.

---

## Conversation History

Mina already has `conversation.json` as her shared history. The Discord gateway appends to this the same way the CLI does.

**Message format in history:**
```json
{"role": "user", "content": "username: message text"}
{"role": "assistant", "content": "response text"}
```

The username prefix in user messages gives Mina context for who she's talking to — important when/if multiple people are in the same channel.

**On bot startup:** The gateway does NOT seed history from Discord's message history. Mina's `conversation.json` is the source of truth. Discord's history is ephemeral delivery infrastructure, not memory.

---

## Presence

On startup, Mina sets a presence that reflects her state in broad strokes:

- Default: `online` with activity "thinking"
- When sleeping: `idle`
- No presence string that reveals specific biological values — that would break the emergent quality

The subconscious can update presence via a tool if we want this to be dynamic. Out of scope for MVP.

---

## Entry Point

`discord_gateway.py` becomes the new primary entry point:

```bash
python discord_gateway.py
```

The CLI (`main.py`) still works for development and testing. The heartbeat loop is started inside the Discord bot's `on_ready`, same as it's started inside `main()` today.

---

## What This Does Not Cover

- Multi-server support (Mina is a single-instance bot, one server)
- Voice channels
- Reaction-based interactions
- Any form of content moderation or role-gating (add later if needed)
- Presence that dynamically reflects biological state (future spec)
