"""
Discord gateway — primary entry point for Mina.

Run via supervisor.py (or directly for development):
    python discord_gateway.py
"""
import asyncio
import json
import os
import re
import sys
import time

import discord
from discord import app_commands

from main import run_turn, heartbeat_loop, load_history, save_history, touch_last_active
from state import load_and_advance, save_state, load_state, apply_deltas, log_state, derived
from memory import build_kag_context, build_rag_context

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_PROJECT_ROOT, "config.json")
_RUN_DIR = os.path.join(_PROJECT_ROOT, "run")
_STOPPED_FLAG = os.path.join(_RUN_DIR, ".stopped")
_READY_FILE = os.path.join(_RUN_DIR, "ready")

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
SEED_MESSAGES = 50
DEBOUNCE_DELAY = 0.1   # seconds — batch rapid messages
CHUNK_SIZE = 1950       # max chars per Discord message


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# Per-channel state
# ---------------------------------------------------------------------------

_pending: dict[int, list[discord.Message]] = {}
_debounce_tasks: dict[int, asyncio.Task] = {}
_inflight: dict[int, asyncio.Task] = {}


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
        # Multiple messages batched — join them
        username = messages[0].author.display_name
        lines = [f"{m.author.display_name}: {m.content}" for m in messages]
        user_input = "\n".join(lines)

    async with channel.typing():
        try:
            reply, image_paths = await run_turn(user_input, username=username)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[GATEWAY ERROR] turn failed: {e}")
            return

    await _deliver(channel, reply, image_paths)

    # Update presence after turn
    state = load_state()
    presence = discord.Status.idle if state.sleeping else discord.Status.online
    await client.change_presence(status=presence)


# ---------------------------------------------------------------------------
# Debounce + inflight management
# ---------------------------------------------------------------------------

async def _debounce_fire(channel: discord.abc.Messageable, channel_id: int) -> None:
    await asyncio.sleep(DEBOUNCE_DELAY)

    messages = _pending.pop(channel_id, [])
    _debounce_tasks.pop(channel_id, None)

    if not messages:
        return

    # Cancel any inflight turn for this channel
    existing = _inflight.get(channel_id)
    if existing and not existing.done():
        existing.cancel()
        try:
            await existing
        except (asyncio.CancelledError, Exception):
            pass

    task = asyncio.create_task(_run_turn(channel, messages))
    _inflight[channel_id] = task

    def _cleanup(t):
        _inflight.pop(channel_id, None)

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
    cfg = _load_config()
    allowlist = [c.lstrip("#") for c in cfg.get("discord_channel_allowlist", [])]

    print(f"[GATEWAY] Logged in as {client.user}")

    # Seed history from Discord for all accessible channels
    seeded_total = 0
    for guild in client.guilds:
        for channel in guild.text_channels:
            if allowlist and channel.name not in allowlist:
                continue
            try:
                n = await _seed_channel(channel)
                if n:
                    print(f"[GATEWAY] Seeded {n} messages from #{channel.name}")
                    seeded_total += n
            except discord.Forbidden:
                pass

    # Sync slash commands
    await tree.sync()
    print("[GATEWAY] Slash commands synced.")

    # Set initial presence
    state = load_state()
    status = discord.Status.idle if state.sleeping else discord.Status.online
    await client.change_presence(status=status, activity=discord.Activity(
        type=discord.ActivityType.listening, name="you"
    ))

    # Start heartbeat
    asyncio.create_task(heartbeat_loop())
    print("[GATEWAY] Heartbeat started.")

    # Write ready file (supervisor/CLI uses this to detect startup)
    os.makedirs(_RUN_DIR, exist_ok=True)
    with open(_READY_FILE, "w") as f:
        f.write(str(time.time()))

    # If messages were seeded, run a turn so Mina can respond to what she missed
    if seeded_total > 0:
        cfg = _load_config()
        default_id = cfg.get("discord_default_channel_id")
        if default_id:
            ch = client.get_channel(int(default_id))
            if ch:
                asyncio.create_task(_run_catchup_turn(ch))

    print("[GATEWAY] Ready.")


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
            print(f"[GATEWAY] Catchup turn error: {e}")
            return
    await _deliver(channel, reply, image_paths)


@client.event
async def on_message(message: discord.Message) -> None:
    if message.author == client.user:
        return
    if message.author.bot:
        return
    if not message.content:
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

    # Cancel existing debounce, start fresh
    existing = _debounce_tasks.get(channel_id)
    if existing and not existing.done():
        existing.cancel()

    task = asyncio.create_task(_debounce_fire(message.channel, channel_id))
    _debounce_tasks[channel_id] = task


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

@tree.command(name="new", description="Clear conversation history. Fresh start.")
async def cmd_new(interaction: discord.Interaction):
    save_history([])
    await interaction.response.send_message("History cleared.", ephemeral=True)


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
    from tools_mina import handle_sleep
    s = load_and_advance()
    _, s = handle_sleep({"duration_hours": hours}, s)
    save_state(s)
    await client.change_presence(status=discord.Status.idle)
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
    await client.change_presence(status=discord.Status.online)
    await interaction.response.send_message("Mina has been woken up.", ephemeral=True)


@tree.command(name="heartbeat", description="Manually trigger one heartbeat cycle.")
async def cmd_heartbeat(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    from heartbeat import run_heartbeat
    try:
        await run_heartbeat()
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


@tree.command(name="stop", description="Stop Mina (supervisor will not restart until 'mina unstop').")
async def cmd_stop(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Stopping. Run `mina unstop` then `mina start` to bring her back.", ephemeral=True
    )
    os.makedirs(_RUN_DIR, exist_ok=True)
    open(_STOPPED_FLAG, "w").close()
    os._exit(0)


@tree.command(name="restart", description="Restart Mina.")
async def cmd_restart(interaction: discord.Interaction):
    await interaction.response.send_message("Restarting...", ephemeral=True)
    os._exit(42)


@tree.command(name="reset", description="Clear history and restart.")
async def cmd_reset(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    # Clean bot messages from this channel
    deleted = 0
    if hasattr(interaction.channel, "purge"):
        def is_mine(m):
            return m.author == client.user
        deleted_msgs = await interaction.channel.purge(limit=100, check=is_mine)
        deleted = len(deleted_msgs)

    save_history([])
    await interaction.followup.send(
        f"Reset: {deleted} message(s) deleted, history cleared. Restarting...",
        ephemeral=True,
    )
    os._exit(42)


@tree.command(name="clean", description="Delete Mina's recent messages in this channel.")
@app_commands.describe(n="Number of messages to delete (default 10)")
async def cmd_clean(interaction: discord.Interaction, n: int = 10):
    await interaction.response.defer(ephemeral=True)
    deleted = 0
    if hasattr(interaction.channel, "purge"):
        def is_mine(m):
            return m.author == client.user
        msgs = await interaction.channel.purge(limit=n * 3, check=is_mine)
        deleted = min(len(msgs), n)
    await interaction.followup.send(f"Deleted {deleted} message(s).", ephemeral=True)


@tree.command(name="status", description="Show Mina's status.")
async def cmd_status(interaction: discord.Interaction):
    cfg = _load_config()
    s = load_state()
    d = derived(s)
    to = d["third_order"]

    sleep_str = f"sleeping (wakes {time.strftime('%H:%M', time.localtime(s.sleep_expected_wake))})" \
        if s.sleeping and s.sleep_expected_wake else ("sleeping" if s.sleeping else "awake")

    lines = [
        f"**Status:** {sleep_str}",
        f"**Compression:** {cfg.get('time_compression_factor', 1.0)}x",
        f"**Heartbeat interval:** {cfg.get('heartbeat_interval_seconds', 1800)}s",
        f"**Mood snapshot:** anxiety={to['anxiety']} depression={to['depression']} "
        f"boredom={to['boredom']} loneliness={to['loneliness']}",
    ]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN not set.", file=sys.stderr)
        sys.exit(1)
    client.run(DISCORD_TOKEN)
