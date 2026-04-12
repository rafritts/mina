"""
Discord gateway — primary entry point for Mina.

Run via supervisor.py (or directly for development):
    python discord_gateway.py
"""
import asyncio
import base64
import json
import logging
import mimetypes
import os
import re
import sys
import tempfile
import time

import base64
import io

import aiohttp
import discord
from discord import app_commands
from PIL import Image

from cortex import run_turn, load_history, save_history, touch_last_active, HISTORY_MAX
from heartbeat import bio_tick_loop
from freetime import run_freetime as _run_freetime
from log import log

# Suppress noisy-but-harmless WebSocket transport errors on reconnect
class _SuppressResetError(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "Cannot write to closing transport" not in (record.getMessage())

logging.getLogger("discord.client").addFilter(_SuppressResetError())
logging.getLogger("discord.gateway").addFilter(_SuppressResetError())
from state import load_and_advance, save_state, load_state, apply_deltas, log_state, derived
from hippocampus import build_kag_context, build_rag_context, rag_wipe

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_PROJECT_ROOT, "config.json")
_RUN_DIR = os.path.join(_PROJECT_ROOT, "run")
_LOG_FILE = os.path.join(_PROJECT_ROOT, "logs", "mina.log")
_STOPPED_FLAG = os.path.join(_RUN_DIR, ".stopped")
_PAUSED_FLAG = os.path.join(_RUN_DIR, ".paused")
_READY_FILE = os.path.join(_RUN_DIR, "ready")
_RESTART_PENDING_FILE = os.path.join(_RUN_DIR, "restart_pending.json")
_OUTBOX_FILE = os.path.join(_RUN_DIR, "outbox.jsonl")
_HOME_CHANNEL_FILE = os.path.join(_RUN_DIR, "home_channel.txt")

DISCORD_TOKEN = os.getenv("MINA_BOT_TOKEN", "")
SEED_MESSAGES = 50
DEBOUNCE_DELAY = 0.1   # seconds — batch rapid messages
CHUNK_SIZE = 1950       # max chars per Discord message
_DEFAULT_AVATAR = os.path.join(_PROJECT_ROOT, "avatar.png")
_DISCORD_API = "https://discord.com/api/v10"

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_IMAGE_MAX_EDGE = 1024   # px — resize before encoding
_IMAGE_MAX_BYTES = 300_000  # 300 KB target


def _normalise_image(data: bytes, mime: str) -> tuple[str, str]:
    """
    Resize to fit within _IMAGE_MAX_EDGE, re-encode as JPEG, and aggressively
    reduce quality + dimensions until under _IMAGE_MAX_BYTES.
    Returns (base64_string, mime_type).
    """
    img = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    max_edge = _IMAGE_MAX_EDGE
    if max(w, h) > max_edge:
        scale = max_edge / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    compressed = b""
    for quality in (80, 70, 60, 50, 40, 30, 20, 10, 5):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed = buf.getvalue()
        if len(compressed) <= _IMAGE_MAX_BYTES:
            return base64.b64encode(compressed).decode("utf-8"), "image/jpeg"

    # Quality reduction alone wasn't enough — halve dimensions and retry
    w2, h2 = img.size
    img = img.resize((w2 // 2, h2 // 2), Image.LANCZOS)
    for quality in (60, 40, 20):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed = buf.getvalue()
        if len(compressed) <= _IMAGE_MAX_BYTES:
            break

    # Return whatever we have — best effort
    return base64.b64encode(compressed).decode("utf-8"), "image/jpeg"


# ---------------------------------------------------------------------------
# Avatar confirm UI
# ---------------------------------------------------------------------------

class _AvatarConfirmView(discord.ui.View):
    def __init__(self, image_path: str, cleanup: bool, cmd_interaction: discord.Interaction):
        super().__init__(timeout=60)
        self.image_path = image_path
        self.cleanup = cleanup
        self.cmd_interaction = cmd_interaction

    @discord.ui.button(label="Upload", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            result = await _change_avatar(os.path.abspath(self.image_path))
            await self.cmd_interaction.delete_original_response()
            await self.cmd_interaction.followup.send(result, ephemeral=True)
        except Exception as e:
            await self.cmd_interaction.followup.send(f"Failed: {e}", ephemeral=True)
        finally:
            if self.cleanup:
                try:
                    os.unlink(self.image_path)
                except FileNotFoundError:
                    pass
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()
        if self.cleanup:
            try:
                os.unlink(self.image_path)
            except FileNotFoundError:
                pass
        self.stop()


async def _change_avatar(image_path: str) -> str:
    """Change the bot avatar via Discord REST API (PATCH /users/@me)."""
    token = os.getenv("MINA_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("MINA_BOT_TOKEN is not set.")

    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type not in {"image/png", "image/jpeg", "image/gif"}:
        raise ValueError("Unsupported format. Use png, jpg, or gif.")

    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("ascii")

    async with aiohttp.ClientSession() as session:
        async with session.patch(
            f"{_DISCORD_API}/users/@me",
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            json={"avatar": f"data:{mime_type};base64,{image_b64}"},
        ) as resp:
            if not (200 <= resp.status < 300):
                body = await resp.text()
                raise RuntimeError(f"Discord API error ({resp.status}): {body}")

    return f"Avatar updated."


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# Presence management
# ---------------------------------------------------------------------------

async def _update_presence(state) -> None:
    """Set Discord presence to reflect Mina's current sleep/wake state."""
    if state.sleeping:
        if state.sleep_expected_wake:
            wake_str = time.strftime("%H:%M", time.localtime(state.sleep_expected_wake))
            activity_name = f"sleeping — wakes ~{wake_str}"
        else:
            activity_name = "sleeping"
        await client.change_presence(
            status=discord.Status.idle,
            activity=discord.Activity(type=discord.ActivityType.watching, name=f"💤 {activity_name}"),
        )
    else:
        await client.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.listening, name="you"),
        )


async def _gateway_freetime_loop() -> None:
    """Periodically run Mina's autonomous freetime session."""
    from config import PAUSED_FLAG, load_config
    while True:
        cfg = load_config()
        interval = int(cfg.get("heartbeat_interval_seconds", 1800))
        await asyncio.sleep(interval)
        if os.path.exists(PAUSED_FLAG):
            log("FREETIME", "Paused — skipping.")
            continue
        log("FREETIME", f"Firing (interval={interval}s)...")
        try:
            await _run_freetime()
        except Exception as e:
            log("FREETIME/ERROR", str(e))


async def _presence_loop() -> None:
    """Poll sleep state every 60s so auto-wake transitions update Discord presence."""
    while True:
        await asyncio.sleep(60)
        try:
            from state import load_state as _load_state
            await _update_presence(_load_state())
        except Exception as e:
            log("PRESENCE/ERROR", str(e))


# ---------------------------------------------------------------------------
# Per-channel state
# ---------------------------------------------------------------------------

_pending: dict[int, list[discord.Message]] = {}
_debounce_tasks: dict[int, asyncio.Task] = {}
_inflight: dict[int, asyncio.Task] = {}
_inflight_messages: dict[int, list[discord.Message]] = {}  # messages currently being processed


# ---------------------------------------------------------------------------
# Text chunking
# ---------------------------------------------------------------------------

def _chunk_text(text: str) -> list[str]:
    """Split text into ≤CHUNK_SIZE chunks on sentence boundaries."""
    if len(text) <= CHUNK_SIZE:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > CHUNK_SIZE:
        # Find last sentence boundary before CHUNK_SIZE
        boundary = -1
        for pattern in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
            idx = remaining.rfind(pattern, 0, CHUNK_SIZE)
            if idx > boundary:
                boundary = idx + len(pattern)

        if boundary <= 0:
            # No sentence boundary — split at last space
            boundary = remaining.rfind(" ", 0, CHUNK_SIZE)
        if boundary <= 0:
            boundary = CHUNK_SIZE

        chunks.append(remaining[:boundary].rstrip())
        remaining = remaining[boundary:].lstrip()

    if remaining:
        chunks.append(remaining)
    return chunks


# ---------------------------------------------------------------------------
# Outbox watcher — delivers messages Mina queued via message_user tool
# ---------------------------------------------------------------------------

async def _outbox_watcher() -> None:
    """Check for outbound messages from Mina every 30 seconds and deliver them."""
    while True:
        await asyncio.sleep(30)
        if not os.path.exists(_OUTBOX_FILE):
            continue
        try:
            with open(_OUTBOX_FILE, "r") as f:
                lines = [l.strip() for l in f if l.strip()]
            if not lines:
                continue
            # Clear outbox before sending (avoid double-sends on error)
            os.remove(_OUTBOX_FILE)
        except (OSError, IOError):
            continue

        # Resolve home channel — prefer last-active, fall back to config default
        channel = None
        channel_id = None
        try:
            with open(_HOME_CHANNEL_FILE) as f:
                channel_id = int(f.read().strip())
        except (FileNotFoundError, ValueError, TypeError):
            pass

        if channel_id is None:
            cfg = _load_config()
            default_id = cfg.get("discord_default_channel_id")
            if default_id:
                channel_id = int(default_id)

        if channel_id is not None:
            channel = client.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await client.fetch_channel(channel_id)
                except Exception:
                    pass

        if channel is None:
            log("OUTBOX", "No channel available — re-queuing messages.")
            with open(_OUTBOX_FILE, "w") as f:
                f.write("\n".join(lines) + "\n")
            continue

        for line in lines:
            try:
                msg = json.loads(line)
                content = msg.get("content", "").strip()
                if content:
                    for chunk in _chunk_text(content):
                        await channel.send(chunk)
                    log("OUTBOX", f"Delivered: {content[:80]}")
            except (json.JSONDecodeError, discord.DiscordException) as e:
                log("OUTBOX/ERROR", str(e))


# ---------------------------------------------------------------------------
# Message delivery
# ---------------------------------------------------------------------------

async def _deliver(channel: discord.abc.Messageable, reply: str, image_paths: list[str]) -> None:
    """Send chunked text then any images to the channel."""
    if reply:
        for chunk in _chunk_text(reply):
            await channel.send(chunk)
            if len(_chunk_text(reply)) > 1:
                await asyncio.sleep(0.15)

    for path in image_paths:
        if os.path.exists(path):
            await channel.send(file=discord.File(path))


# ---------------------------------------------------------------------------
# Turn runner
# ---------------------------------------------------------------------------

async def _run_turn(channel: discord.abc.Messageable, messages: list[discord.Message]) -> None:
    """Execute one Mina turn for a batch of Discord messages."""
    touch_last_active()

    # Format batched messages as a single user input
    if len(messages) == 1:
        user_input = messages[0].content
        username = messages[0].author.display_name
    else:
        username = messages[0].author.display_name
        lines = [f"{m.author.display_name}: {m.content}" for m in messages]
        user_input = "\n".join(lines)

    # Collect first image attachment across all batched messages
    image_b64 = None
    image_mime = "image/jpeg"
    for msg in messages:
        for att in msg.attachments:
            content_type = (att.content_type or "").split(";")[0].strip()
            if content_type in _IMAGE_TYPES:
                try:
                    async with aiohttp.ClientSession() as http:
                        async with http.get(att.url) as resp:
                            if resp.status == 200:
                                raw = await resp.read()
                                image_b64, image_mime = _normalise_image(raw, content_type)
                                out_kb = len(base64.b64decode(image_b64)) // 1024
                                over = "⚠ OVER LIMIT" if out_kb > 300 else "ok"
                                log("VISION", f"{att.filename} {len(raw)//1024}KB → {out_kb}KB ({over})")
                except Exception as e:
                    log("VISION/ERROR", f"{att.filename}: {e}")
                break
        if image_b64:
            break

    try:
        async with channel.typing():
            reply, image_paths = await run_turn(
                user_input, username=username,
                image_b64=image_b64, image_mime=image_mime,
            )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log("GATEWAY/ERROR", f"turn failed: {e}")
        return

    await _deliver(channel, reply, image_paths)

    # Update presence after turn
    await _update_presence(load_state())


# ---------------------------------------------------------------------------
# Debounce + inflight management
# ---------------------------------------------------------------------------

async def _debounce_fire(channel: discord.abc.Messageable, channel_id: int) -> None:
    await asyncio.sleep(DEBOUNCE_DELAY)

    messages = _pending.pop(channel_id, [])
    _debounce_tasks.pop(channel_id, None)

    if not messages:
        return

    # Cancel any inflight turn and rescue its messages
    existing = _inflight.get(channel_id)
    if existing and not existing.done():
        rescued = _inflight_messages.pop(channel_id, [])
        existing.cancel()
        try:
            await existing
        except (asyncio.CancelledError, Exception):
            pass
        # Prepend rescued messages so they aren't lost
        if rescued:
            log("GATEWAY", f"Rescued {len(rescued)} in-flight message(s) for channel {channel_id}")
            messages = rescued + messages

    _inflight_messages[channel_id] = messages
    task = asyncio.create_task(_run_turn(channel, messages))
    _inflight[channel_id] = task

    def _cleanup(t):
        _inflight.pop(channel_id, None)
        _inflight_messages.pop(channel_id, None)

    task.add_done_callback(_cleanup)


# ---------------------------------------------------------------------------
# History seeding
# ---------------------------------------------------------------------------

async def _seed_channel(channel: discord.TextChannel) -> int:
    """
    Fetch recent Discord history and append to conversation.json.
    Returns number of messages seeded.
    """
    history = load_history()

    # Collect recent messages (oldest first)
    messages = []
    async for msg in channel.history(limit=SEED_MESSAGES, oldest_first=False):
        if msg.author.bot:
            continue
        if not msg.content:
            continue
        messages.append(msg)
    messages.reverse()  # chronological order

    if not messages:
        return 0

    # Deduplication: check if the last message is already in history
    last_content = f"{messages[-1].author.display_name}: {messages[-1].content}"
    for entry in reversed(history):
        if entry.get("role") == "user" and entry.get("content", "").endswith(messages[-1].content):
            return 0  # Already seeded

    # Append seed marker + messages
    history.append({"role": "system", "content": "[DISCORD_SEED]"})
    for msg in messages:
        history.append({
            "role": "user",
            "content": f"{msg.author.display_name}: {msg.content}",
        })

    save_history(history)
    return len(messages)


# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready():
    import token_stats
    token_stats.reset()

    cfg = _load_config()
    allowlist = [c.lstrip("#") for c in cfg.get("discord_channel_allowlist", [])]

    log("GATEWAY", f"Logged in as {client.user}")

    # Seed history from Discord for all accessible channels
    seeded_total = 0
    for guild in client.guilds:
        for channel in guild.text_channels:
            if allowlist and channel.name not in allowlist:
                continue
            try:
                n = await _seed_channel(channel)
                if n:
                    log("GATEWAY", f"Seeded {n} messages from #{channel.name}")
                    seeded_total += n
            except discord.Forbidden:
                pass

    # Sync slash commands
    await tree.sync()
    log("GATEWAY", "Slash commands synced.")

    # Set initial presence
    await _update_presence(load_state())

    # Start background loops
    asyncio.create_task(bio_tick_loop())
    asyncio.create_task(_gateway_freetime_loop())
    asyncio.create_task(_outbox_watcher())
    asyncio.create_task(_presence_loop())
    log("GATEWAY", "Bio tick, freetime, outbox watcher, and presence loop started.")

    # Write ready file (supervisor/CLI uses this to detect startup)
    os.makedirs(_RUN_DIR, exist_ok=True)
    with open(_READY_FILE, "w") as f:
        f.write(str(time.time()))

    # If a /restart was pending, update the ephemeral message now that we're back
    if os.path.exists(_RESTART_PENDING_FILE):
        try:
            with open(_RESTART_PENDING_FILE) as f:
                pending = json.load(f)
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as http:
                await http.patch(
                    f"{_DISCORD_API}/webhooks/{pending['application_id']}/{pending['token']}/messages/@original",
                    json={"content": "✅ Back online."},
                )
        except Exception as e:
            log("GATEWAY/ERROR", f"Failed to update restart message: {e}")
        finally:
            try:
                os.remove(_RESTART_PENDING_FILE)
            except FileNotFoundError:
                pass

    # If messages were seeded, run a turn so Mina can respond to what she missed
    if seeded_total > 0:
        cfg = _load_config()
        default_id = cfg.get("discord_default_channel_id")
        if default_id:
            ch = client.get_channel(int(default_id))
            if ch:
                asyncio.create_task(_run_catchup_turn(ch))

    log("GATEWAY", "Ready.")


async def _run_catchup_turn(channel: discord.abc.Messageable) -> None:
    """Run a turn after seeding so Mina responds to messages she missed."""
    await asyncio.sleep(1)  # Brief pause after on_ready settles
    async with channel.typing():
        try:
            reply, image_paths = await run_turn(
                "[Mina just came back online and is reading messages she missed]",
                username="system",
            )
        except Exception as e:
            log("GATEWAY/ERROR", f"Catchup turn: {e}")
            return
    await _deliver(channel, reply, image_paths)


@client.event
async def on_message(message: discord.Message) -> None:
    if message.author == client.user:
        return
    if message.author.bot:
        return
    # Allow image-only messages (no text content) — attachments are handled downstream
    if not message.content and not message.attachments:
        return

    cfg = _load_config()
    allowlist = [c.lstrip("#") for c in cfg.get("discord_channel_allowlist", [])]

    # Channel filter
    if allowlist and isinstance(message.channel, discord.TextChannel):
        if message.channel.name not in allowlist:
            return

    # DM filter
    if isinstance(message.channel, discord.DMChannel):
        if not cfg.get("discord_enable_dms", True):
            return

    channel_id = message.channel.id
    _pending.setdefault(channel_id, []).append(message)

    # Track home channel so the outbox watcher knows where to send unprompted messages
    with open(_HOME_CHANNEL_FILE, "w") as _f:
        _f.write(str(channel_id))

    # Cancel existing debounce, start fresh
    existing = _debounce_tasks.get(channel_id)
    if existing and not existing.done():
        existing.cancel()

    task = asyncio.create_task(_debounce_fire(message.channel, channel_id))
    _debounce_tasks[channel_id] = task


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Wipe helper (used by /reset and /factory-reset)
# ---------------------------------------------------------------------------

def _wipe_user_data() -> list[str]:
    wiped = []
    for rel_path in ["run/conversation.json"]:
        dst = os.path.join(_PROJECT_ROOT, rel_path)
        if os.path.exists(dst):
            os.remove(dst)
            wiped.append(rel_path)
    kag_dir = os.path.join(_PROJECT_ROOT, "memory", "kag")
    if os.path.exists(kag_dir):
        for root, dirs, files in os.walk(kag_dir):
            for fname in files:
                full = os.path.join(root, fname)
                os.remove(full)
                wiped.append(os.path.relpath(full, _PROJECT_ROOT).replace(os.sep, "/"))
    os.makedirs(kag_dir, exist_ok=True)
    rel_md = os.path.join(kag_dir, "RELATIONSHIP.md")
    with open(rel_md, "w") as f:
        f.write("# Relationship with User\n\nNo history yet.\n")
    wiped.append("memory/kag/RELATIONSHIP.md (reset to blank)")
    try:
        rag_wipe()  # imported from hippocampus at top of file
        wiped.append("memory/rag/ (RAG wiped)")
    except Exception as e:
        wiped.append(f"memory/rag/ (wipe failed: {e})")
    return wiped


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

@tree.command(name="new", description="Clear conversation history and restart.")
async def cmd_new(interaction: discord.Interaction):
    save_history([])
    await interaction.response.send_message("History cleared. Restarting...", ephemeral=True)
    os.makedirs(_RUN_DIR, exist_ok=True)
    with open(_RESTART_PENDING_FILE, "w") as f:
        json.dump({"token": interaction.token, "application_id": interaction.application_id}, f)
    os._exit(42)


@tree.command(name="reset", description="Wipe Mina's memory, state, and history.")
async def cmd_reset(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        wiped = _wipe_user_data()
        os.makedirs(_RUN_DIR, exist_ok=True)
        with open(_RESTART_PENDING_FILE, "w") as f:
            json.dump({"token": interaction.token, "application_id": interaction.application_id}, f)
        await interaction.followup.send(f"Reset complete. Restarting...\nWiped: {', '.join(wiped)}", ephemeral=True)
        os._exit(42)
    except Exception as e:
        await interaction.followup.send(f"Reset failed: {e}", ephemeral=True)


@tree.command(name="factory-reset", description="Nuclear reset: wipe everything including biomarkers.")
async def cmd_factory_reset(interaction: discord.Interaction):
    from state import BiologicalState, save_state
    await interaction.response.defer(ephemeral=True)
    try:
        wiped = _wipe_user_data()
        save_state(BiologicalState())
        wiped.append("state.json (biomarkers reset to defaults)")
        os.makedirs(_RUN_DIR, exist_ok=True)
        with open(_RESTART_PENDING_FILE, "w") as f:
            json.dump({"token": interaction.token, "application_id": interaction.application_id}, f)
        await interaction.followup.send(f"Factory reset complete. Restarting...\nWiped: {', '.join(wiped)}", ephemeral=True)
        os._exit(42)
    except Exception as e:
        await interaction.followup.send(f"Factory reset failed: {e}", ephemeral=True)


@tree.command(name="history", description="Show recent conversation history.")
@app_commands.describe(n="Number of entries to show (default 10)")
async def cmd_history(interaction: discord.Interaction, n: int = 10):
    history = load_history()
    entries = [e for e in history if e.get("role") in ("user", "assistant")][-n:]
    if not entries:
        await interaction.response.send_message("No history yet.", ephemeral=True)
        return
    lines = []
    for e in entries:
        role = "Mina" if e["role"] == "assistant" else "User"
        content = e.get("content", "")[:200]
        lines.append(f"**{role}:** {content}")
    await interaction.response.send_message("\n".join(lines)[:1900], ephemeral=True)


@tree.command(name="actions", description="Show Mina's recent tool calls and their effects.")
@app_commands.describe(n="Number of actions to show (default 10)")
async def cmd_actions(interaction: discord.Interaction, n: int = 10):
    from events import read_events
    all_events = read_events(limit=300)
    tool_events = [e for e in all_events if e.get("type") == "tool"][:n]
    if not tool_events:
        await interaction.response.send_message("No tool calls recorded yet.", ephemeral=True)
        return

    lines = []
    for e in tool_events:
        tool = e.get("tool", "?")
        args = e.get("args", {})
        result = e.get("result", "")
        deltas = e.get("deltas", {})
        source = e.get("source", "")
        ts = e.get("ts", 0)

        delta = time.time() - ts
        if delta < 60:    age = "just now"
        elif delta < 3600: age = f"{int(delta/60)}m ago"
        elif delta < 86400: age = f"{int(delta/3600)}h ago"
        else:              age = f"{int(delta/86400)}d ago"

        # Format args as a readable summary
        if tool == "do_action":
            summary = args.get("activity", "")
        elif tool == "sleep":
            summary = f"{args.get('duration_hours', '?')}h"
        elif tool in ("web_search", "x_search"):
            summary = args.get("query", "")
        else:
            summary = ", ".join(f"{k}={v}" for k, v in args.items()) if args else ""

        # Format deltas
        delta_str = ""
        if deltas:
            CHEM_SHORT = {
                "cortisol": "cort", "norepinephrine": "norepi", "dopamine": "dopa",
                "serotonin": "sero", "oxytocin": "oxy", "endorphins": "endo",
                "acetylcholine": "ach", "melatonin": "mela", "glucose": "gluc",
                "hydration": "hydr", "sleep_pressure": "sleep",
            }
            parts = []
            for k, v in deltas.items():
                short = CHEM_SHORT.get(k, k)
                sign = "+" if v > 0 else ""
                parts.append(f"{short}{sign}{v:.1f}")
            delta_str = f" `{' '.join(parts)}`"

        src_tag = f" _{source}_" if source else ""
        lines.append(f"**{tool}** {summary}{src_tag} · {age}{delta_str}")
        if result and tool not in ("generate_image",):
            lines.append(f"  ↳ {result[:120]}")

    await interaction.response.send_message("\n".join(lines)[:1900], ephemeral=True)


@tree.command(name="state", description="Show Mina's current biological state.")
async def cmd_state(interaction: discord.Interaction):
    from state import derived as _derived
    s = load_and_advance()
    d = _derived(s)
    so = d["second_order"]
    to = d["third_order"]

    lines = [
        "**First-order**",
        f"sleep_pressure={s.sleep_pressure:.1f}  glucose={s.glucose:.1f}  hydration={s.hydration:.1f}",
        f"cortisol={s.cortisol:.1f}  dopamine={s.dopamine:.1f}  serotonin={s.serotonin:.1f}",
        f"norepi={s.norepinephrine:.1f}  oxytocin={s.oxytocin:.1f}  endorphins={s.endorphins:.1f}",
        f"acetylcholine={s.acetylcholine:.1f}  melatonin={s.melatonin:.1f}  sleeping={s.sleeping}",
        "",
        "**Second-order**",
        f"energy={so['energy']}  clarity={so['cognitive_clarity']}  hedonic={so['hedonic_tone']}",
        f"warmth={so['social_warmth']}  arousal={so['arousal']}  valence={so['mood_valence']}",
        "",
        "**Third-order**",
        f"anxiety={to['anxiety']}  depression={to['depression']}  boredom={to['boredom']}",
        f"loneliness={to['loneliness']}  flow={to['flow']}",
    ]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@tree.command(name="bioreport", description="Show Mina's current biological state.")
async def cmd_bioreport(interaction: discord.Interaction):
    from chemicals import get_label
    from state import derived as _derived
    s = load_and_advance()
    d = _derived(s)
    so = d["second_order"]
    to = d["third_order"]

    def lbl(name: str) -> str:
        val = s.chemicals.get(name, 0.0)
        label, _ = get_label(name, val)
        return label.title()

    sleeping_str = " — sleeping" if s.sleeping else ""
    now_str = time.strftime("%a %b %-d  %-I:%M %p")

    lines = [
        f"**{now_str}{sleeping_str}**",
        "",
        "**Body**",
        f"Glucose: {lbl('glucose')}",
        f"Hydration: {lbl('hydration')}",
        f"Sleep pressure: {lbl('sleep_pressure')}",
        "",
        "**Chemistry**",
        f"Cortisol: {lbl('cortisol')}",
        f"Dopamine: {lbl('dopamine')}",
        f"Serotonin: {lbl('serotonin')}",
        f"Norepinephrine: {lbl('norepinephrine')}",
        f"Oxytocin: {lbl('oxytocin')}",
        f"Endorphins: {lbl('endorphins')}",
        f"Acetylcholine: {lbl('acetylcholine')}",
        f"Melatonin: {lbl('melatonin')}",
        "",
        "**State**",
        f"Energy: {so['energy']:.0f}  Clarity: {so['cognitive_clarity']:.0f}  Mood: {so['mood_valence']:.0f}",
        f"Anxiety: {to['anxiety']:.0f}  Depression: {to['depression']:.0f}  Loneliness: {to['loneliness']:.0f}",
        f"Boredom: {to['boredom']:.0f}  Flow: {to['flow']:.0f}",
    ]

    if s.substances:
        from src.sim.neuro.substances import SUBSTANCE_DEFS
        lines.append("")
        lines.append("**Active substances**")
        for name, dose in s.substances.items():
            sub = SUBSTANCE_DEFS.get(name, {})
            level = dose.get("level", 0)
            lines.append(f"{sub.get('display_name', name)}: {level:.0f}/100")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@tree.command(name="compress", description="Set time compression factor.")
@app_commands.describe(factor="Multiplier (e.g. 10 = 10x faster biological time)")
async def cmd_compress(interaction: discord.Interaction, factor: float):
    cfg = _load_config()
    cfg["time_compression_factor"] = factor
    with open(_CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    await interaction.response.send_message(
        f"Time compression set to {factor}x.", ephemeral=True
    )


@tree.command(name="sleep", description="Put Mina to sleep.")
@app_commands.describe(hours="How many simulated hours to sleep")
async def cmd_sleep(interaction: discord.Interaction, hours: float = 8.0):
    from tools import handle_sleep
    s = load_and_advance()
    _, s = handle_sleep({"duration_hours": hours}, s)
    save_state(s)
    await _update_presence(s)
    await interaction.response.send_message(
        f"Mina is going to sleep for {hours:.1f} simulated hours.", ephemeral=True
    )


@tree.command(name="wake", description="Force-wake Mina (she'll be groggy).")
async def cmd_wake(interaction: discord.Interaction):
    s = load_and_advance()
    s.sleeping = False
    s.sleep_start = None
    s.sleep_expected_wake = None
    # Groggy waking — cortisol spike, suppressed acetylcholine
    s = apply_deltas(s, {"cortisol": 20, "norepinephrine": 12, "acetylcholine": -15})
    save_state(s)
    await _update_presence(s)
    await interaction.response.send_message("Mina has been woken up.", ephemeral=True)


@tree.command(name="heartbeat", description="Manually trigger one heartbeat cycle.")
async def cmd_heartbeat(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    from freetime import run_freetime
    try:
        await run_freetime()
        await interaction.followup.send("Heartbeat complete.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Heartbeat error: {e}", ephemeral=True)


@tree.command(name="cancel", description="Cancel current turn in this channel.")
async def cmd_cancel(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    stopped = False

    dbt = _debounce_tasks.get(channel_id)
    if dbt and not dbt.done():
        dbt.cancel()
        _pending.pop(channel_id, None)
        _debounce_tasks.pop(channel_id, None)
        stopped = True

    inf = _inflight.get(channel_id)
    if inf and not inf.done():
        inf.cancel()
        stopped = True

    msg = "Cancelled." if stopped else "Nothing to cancel."
    await interaction.response.send_message(msg, ephemeral=True)


@tree.command(name="cancel-all", description="Cancel all running turns.")
async def cmd_cancel_all(interaction: discord.Interaction):
    count = 0
    for task in list(_debounce_tasks.values()):
        if not task.done():
            task.cancel()
            count += 1
    _debounce_tasks.clear()
    _pending.clear()

    for task in list(_inflight.values()):
        if not task.done():
            task.cancel()
            count += 1

    await interaction.response.send_message(
        f"Cancelled {count} task(s)." if count else "Nothing to cancel.",
        ephemeral=True,
    )


@tree.command(name="set-avatar", description="Set Mina's avatar. Attach an image, or leave blank to use avatar.png.")
@app_commands.describe(image="Image to upload (png, jpg, gif). Leave blank to use avatar.png in the repo.")
async def cmd_set_avatar(interaction: discord.Interaction, image: discord.Attachment = None):
    cleanup = False
    if image is not None:
        suffix = os.path.splitext(image.filename)[1] or ".png"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        async with aiohttp.ClientSession() as http:
            async with http.get(image.url) as resp:
                tmp.write(await resp.read())
        tmp.close()
        actual_path = tmp.name
        cleanup = True
    else:
        if not os.path.exists(_DEFAULT_AVATAR):
            await interaction.response.send_message(
                f"No `avatar.png` found in the repo root. Attach an image instead.", ephemeral=True
            )
            return
        actual_path = _DEFAULT_AVATAR

    view = _AvatarConfirmView(actual_path, cleanup, interaction)
    await interaction.response.send_message(
        "Upload this as Mina's avatar?",
        file=discord.File(actual_path, filename=os.path.basename(actual_path)),
        view=view,
        ephemeral=True,
    )


@tree.command(name="pause", description="Pause biological updating (no time decay, no heartbeat).")
async def cmd_pause(interaction: discord.Interaction):
    os.makedirs(_RUN_DIR, exist_ok=True)
    open(_PAUSED_FLAG, "w").close()
    await interaction.response.send_message("Biological updates paused.", ephemeral=True)


@tree.command(name="resume", description="Resume biological updating.")
async def cmd_resume(interaction: discord.Interaction):
    try:
        os.remove(_PAUSED_FLAG)
    except FileNotFoundError:
        pass
    await interaction.response.send_message("Biological updates resumed.", ephemeral=True)


@tree.command(name="stop", description="Stop Mina (supervisor will not restart until 'mina unstop').")
async def cmd_stop(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Stopping. Run `mina unstop` then `mina start` to bring her back.", ephemeral=True
    )
    os.makedirs(_RUN_DIR, exist_ok=True)
    open(_STOPPED_FLAG, "w").close()
    await asyncio.sleep(0.5)
    os._exit(0)


@tree.command(name="restart", description="Restart Mina.")
async def cmd_restart(interaction: discord.Interaction):
    await interaction.response.send_message("Restarting... this message will update when she's back.", ephemeral=True)
    os.makedirs(_RUN_DIR, exist_ok=True)
    with open(_RESTART_PENDING_FILE, "w") as f:
        json.dump({"token": interaction.token, "application_id": interaction.application_id}, f)
    os._exit(42)



@tree.command(name="clean", description="Delete Mina's messages in this channel.")
@app_commands.describe(n="Number of messages to delete (default: all)")
async def cmd_clean(interaction: discord.Interaction, n: int = 0):
    await interaction.response.defer(ephemeral=True)
    channel = interaction.channel or await client.fetch_channel(interaction.channel_id)

    scan_limit = (n * 5) if n > 0 else 500
    deleted_count = 0
    found = 0
    try:
        async for msg in channel.history(limit=scan_limit, oldest_first=False):
            if msg.author != client.user:
                continue
            await msg.delete()
            deleted_count += 1
            await asyncio.sleep(0.5)
            found += 1
            if n > 0 and found >= n:
                break
    except discord.HTTPException as e:
        await interaction.followup.send(f"Deleted {deleted_count} before error: {e}", ephemeral=True)
        return

    await interaction.followup.send(f"Deleted {deleted_count} message(s).", ephemeral=True)


@tree.command(name="context", description="Show Mina's context window, bio state, and config.")
async def cmd_context(interaction: discord.Interaction):
    cfg = _load_config()
    s = load_state()
    d = derived(s)
    to = d["third_order"]

    # --- Conversation stats ---
    history = load_history()
    # HISTORY_MAX already imported from cortex at top of file
    total_msgs = len(history)
    role_counts: dict[str, int] = {}
    for m in history:
        role = m.get("role", "?")
        role_counts[role] = role_counts.get(role, 0) + 1
    pct = (total_msgs / HISTORY_MAX * 100) if HISTORY_MAX else 0
    bar_filled = min(20, int(pct / 5))
    bar = "\u2588" * bar_filled + "\u2591" * (20 - bar_filled)
    role_str = "  ".join(f"{r}: {c}" for r, c in sorted(role_counts.items()))

    # --- Reflection ---
    from hippocampus import read_kag
    reflection_text = read_kag("REFLECTION.md") or ""
    reflection_words = len(reflection_text.split()) if reflection_text else 0
    reflection_preview = (
        reflection_text[:120].replace("\n", " ") + ("…" if len(reflection_text) > 120 else "")
        if reflection_text else "(empty)"
    )

    # --- Bio state ---
    so = d["second_order"]
    sleep_str = (
        f"sleeping (wakes {time.strftime('%H:%M', time.localtime(s.sleep_expected_wake))})"
        if s.sleeping and s.sleep_expected_wake
        else ("sleeping" if s.sleeping else "awake")
    )

    lines = [
        "**Mina — Context**",
        "```",
        "Conversation",
        f"  Messages:  {total_msgs} / {HISTORY_MAX}  ({pct:.1f}%)",
        f"  Progress:  [{bar}]",
        f"  Breakdown: {role_str}",
        "",
        "Reflection",
        f"  Words:     {reflection_words}",
        f"  Preview:   {reflection_preview}",
        "",
        "Biological State",
        f"  Status:    {sleep_str}",
        f"  First:     cortisol={s.cortisol:.0f}  dopamine={s.dopamine:.0f}  serotonin={s.serotonin:.0f}  "
        f"oxytocin={s.oxytocin:.0f}",
        f"  Second:    energy={so['energy']}  clarity={so['cognitive_clarity']}  "
        f"valence={so['mood_valence']}",
        f"  Third:     anxiety={to['anxiety']}  depression={to['depression']}  "
        f"boredom={to['boredom']}  loneliness={to['loneliness']}",
        "",
        "Config",
        f"  Compression: {cfg.get('time_compression_factor', 1.0)}x  "
        f"Heartbeat: {cfg.get('heartbeat_interval_seconds', 1800)}s  "
        f"Paused: {os.path.exists(_PAUSED_FLAG)}",
        "```",
    ]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("ERROR: MINA_BOT_TOKEN not set.", file=sys.stderr)
        sys.exit(1)
    client.run(DISCORD_TOKEN)
