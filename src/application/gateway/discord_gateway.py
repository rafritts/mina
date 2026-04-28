"""
Discord gateway — primary entry point for Mina.

Run via supervisor.py (or directly for development):
    python discord_gateway.py
"""
import asyncio
import base64
import json
import logging
import os
import re
import sys
import time

import aiohttp
import discord
from discord import app_commands
from dotenv import load_dotenv, find_dotenv

_DOTENV = find_dotenv(usecwd=True)
load_dotenv(_DOTENV)
_PROJECT_ROOT = os.path.dirname(_DOTENV)

from src.brain.cortex.cortex import run_turn, load_history, save_history, touch_last_active
from src.brain.brainstem.heartbeat import bio_tick_loop
from src.brain.subconscious.freetime import run_freetime as _run_freetime
from ..infra.log import log
from ..infra import discord_send as _discord_send
from ..infra.image_utils import normalise_image as _normalise_image

# Suppress noisy-but-harmless WebSocket transport errors on reconnect
class _SuppressResetError(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "Cannot write to closing transport" not in record.getMessage()

logging.getLogger("discord.client").addFilter(_SuppressResetError())
logging.getLogger("discord.gateway").addFilter(_SuppressResetError())

from src.brain.brainstem.state import load_and_advance, save_state, load_state, apply_deltas, derived
from src.config.config import PAUSED_FLAG, RUN_DIR, REPO_ROOT

_RUN_DIR              = RUN_DIR
_READY_FILE           = os.path.join(_RUN_DIR, "ready")
_RESTART_PENDING_FILE = os.path.join(_RUN_DIR, "restart_pending.json")
_HOME_CHANNEL_FILE    = os.path.join(_RUN_DIR, "home_channel.txt")
_DISCORD_API          = "https://discord.com/api/v10"

DISCORD_TOKEN = os.getenv("MINA_BOT_TOKEN", "")
SEED_MESSAGES = 50
DEBOUNCE_DELAY = 0.1
CHUNK_SIZE = 1950

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Register mina.log as a stream bus consumer
try:
    from src.application.infra.stream_bus import stream_bus as _stream_bus
    from ..infra.log import log as _log

    _SKIP_LOG_EVENTS = frozenset({
        "state_snapshot",   # every-60s heartbeat dump — dashboard only
        "emotion_pillar",   # duplicate of [EMOTION_PILLAR] log line
        "context_pillar",   # duplicate of [CONTEXT_PILLAR] log line
        "reasoning",        # duplicate of [REASONER] log line
        "stimulus_land",    # redundant with [ENCODER/STIMULUS]
        "delta",            # redundant with encoder logs
        "rag_hit",          # verbose per-hit noise
        "kag_selection",    # verbose per-file noise
    })

    def _stream_log_handler(event) -> None:
        if event.type in _SKIP_LOG_EVENTS:
            return
        import json as _json
        _log(event.type.upper(), _json.dumps(event.payload))

    _stream_bus.register(_stream_log_handler)
except Exception:
    pass


# ---------------------------------------------------------------------------
# Presence management
# ---------------------------------------------------------------------------

async def _update_presence(state) -> None:
    if not client.is_ready():
        return
    if state.sleeping:
        if state.sleep_expected_wake:
            wake_str = time.strftime("%H:%M", time.localtime(state.sleep_expected_wake))
            activity_name = f"sleeping — wakes ~{wake_str}"
        else:
            activity_name = "sleeping"
        await client.change_presence(
            status=discord.Status.dnd,
            activity=discord.Activity(type=discord.ActivityType.watching, name=f"💤 {activity_name}"),
        )
    else:
        await client.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.listening, name="you"),
        )


def _dynamic_freetime_interval(base_seconds: int) -> int:
    try:
        state = load_state()
        if state.sleeping:
            return min(base_seconds * 4, base_seconds * 6)

        d = derived(state)
        energy    = d["second_order"].get("energy", 50.0)
        sleep_p   = state.sleep_pressure
        melatonin = state.chemicals.get("melatonin", 5.0)

        if energy >= 70:      energy_factor = 0.6
        elif energy >= 50:    energy_factor = 0.85
        elif energy >= 30:    energy_factor = 1.3
        else:                 energy_factor = 2.0

        if sleep_p >= 75:     sleep_factor = 2.0
        elif sleep_p >= 55:   sleep_factor = 1.4
        else:                 sleep_factor = 1.0

        if melatonin < 15:    melatonin_factor = 0.7
        elif melatonin < 80:  melatonin_factor = 1.2
        else:                 melatonin_factor = 2.5

        scale    = energy_factor * sleep_factor * melatonin_factor
        interval = int(base_seconds * scale)
        lo       = max(300, base_seconds // 4)
        hi       = base_seconds * 6
        return max(lo, min(hi, interval))
    except Exception:
        return base_seconds


# ---------------------------------------------------------------------------
# Background loops
# ---------------------------------------------------------------------------

async def _gateway_freetime_loop() -> None:
    from src.config.config import load_config
    while True:
        cfg      = load_config()
        base     = int(cfg.get("heartbeat_interval_seconds", 1800))
        interval = _dynamic_freetime_interval(base)
        log("FREETIME", f"Next session in {interval}s (base={base}s).")
        await asyncio.sleep(interval)
        if os.path.exists(PAUSED_FLAG):
            log("FREETIME", "Paused — skipping.")
            continue
        log("FREETIME", "Firing...")
        try:
            await _run_freetime()
        except Exception as e:
            import traceback
            log("FREETIME/ERROR", str(e) + "\n" + traceback.format_exc())


async def _presence_loop() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await _update_presence(load_state())
        except Exception as e:
            log("PRESENCE/ERROR", str(e))


async def _followup_watcher() -> None:
    from src.brain.cortex.followup import process_due_followups
    while True:
        await asyncio.sleep(60)
        try:
            await process_due_followups()
        except Exception as e:
            log("FOLLOWUP/ERR", f"Watcher error: {e}")


# ---------------------------------------------------------------------------
# Per-channel state
# ---------------------------------------------------------------------------

_pending: dict[int, list[discord.Message]] = {}
_debounce_tasks: dict[int, asyncio.Task] = {}
_inflight: dict[int, asyncio.Task] = {}
_inflight_messages: dict[int, list[discord.Message]] = {}
_pending_wake: dict[int, list[discord.Message]] = {}

_WAKE_NO_RE = re.compile(r"^\s*(no+|nope|nah|nevermind|never\s*mind|cancel|don'?t)\s*[.!]?\s*$", re.I)


# ---------------------------------------------------------------------------
# Text chunking + delivery
# ---------------------------------------------------------------------------

def _chunk_text(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks = []
    remaining = text
    while len(remaining) > CHUNK_SIZE:
        boundary = -1
        for pattern in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
            idx = remaining.rfind(pattern, 0, CHUNK_SIZE)
            if idx > boundary:
                boundary = idx + len(pattern)
        if boundary <= 0:
            boundary = remaining.rfind(" ", 0, CHUNK_SIZE)
        if boundary <= 0:
            boundary = CHUNK_SIZE
        chunks.append(remaining[:boundary].rstrip())
        remaining = remaining[boundary:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


async def _deliver(channel: discord.abc.Messageable, reply: str, image_paths: list[str]) -> None:
    if reply:
        chunks = _chunk_text(reply)
        for chunk in chunks:
            await channel.send(chunk)
            if len(chunks) > 1:
                await asyncio.sleep(0.15)
    for path in image_paths:
        if os.path.exists(path):
            await channel.send(file=discord.File(path))


# ---------------------------------------------------------------------------
# Channel resolver + outbox sender
# ---------------------------------------------------------------------------

async def _resolve_home_channel() -> discord.abc.Messageable | None:
    channel_id = None
    try:
        with open(_HOME_CHANNEL_FILE) as f:
            channel_id = int(f.read().strip())
    except (FileNotFoundError, ValueError, TypeError):
        pass

    if channel_id is None:
        from src.config.config import load_config
        default_id = load_config().get("discord_default_channel_id")
        if default_id:
            channel_id = int(default_id)

    if channel_id is None:
        return None

    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except Exception:
            pass
    return channel


async def _do_send(content: str = "", image_path: str = "") -> None:
    channel = await _resolve_home_channel()
    if channel is None:
        log("SEND", "No channel available — message dropped.")
        return
    try:
        if content:
            for chunk in _chunk_text(content):
                await channel.send(chunk)
            log("SEND", f"Delivered: {content}")
        if image_path and os.path.exists(image_path):
            await channel.send(file=discord.File(image_path))
            log("SEND", f"Delivered image: {os.path.basename(image_path)}")
    except discord.DiscordException as e:
        log("SEND/ERROR", str(e))


# ---------------------------------------------------------------------------
# Turn runner
# ---------------------------------------------------------------------------

async def _run_turn(channel: discord.abc.Messageable, messages: list[discord.Message]) -> None:
    touch_last_active()

    if len(messages) == 1:
        user_input = messages[0].content
        username = messages[0].author.display_name
    else:
        username = messages[0].author.display_name
        lines = [f"{m.author.display_name}: {m.content}" for m in messages]
        user_input = "\n".join(lines)

    images: list[tuple[str, str]] = []
    for msg in messages:
        for att in msg.attachments:
            content_type = (att.content_type or "").split(";")[0].strip()
            if content_type in _IMAGE_TYPES:
                try:
                    async with aiohttp.ClientSession() as http:
                        async with http.get(att.url) as resp:
                            if resp.status == 200:
                                raw = await resp.read()
                                b64, mime = _normalise_image(raw, content_type)
                                out_kb = len(base64.b64decode(b64)) // 1024
                                over = "⚠ OVER LIMIT" if out_kb > 300 else "ok"
                                log("VISION", f"{att.filename} {len(raw)//1024}KB → {out_kb}KB ({over})")
                                images.append((b64, mime))
                except Exception as e:
                    log("VISION/ERROR", f"{att.filename}: {e}")

    try:
        async with channel.typing():
            reply, image_paths = await run_turn(
                user_input, username=username,
                images=images or None,
            )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log("GATEWAY/ERROR", f"turn failed: {e}")
        return

    await _deliver(channel, reply, image_paths)
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

    _state = load_state()
    if channel_id in _pending_wake:
        held = _pending_wake.pop(channel_id)
        combined = " ".join(m.content for m in messages).strip()
        if _WAKE_NO_RE.match(combined):
            return
        _state.sleeping = False
        _state.sleep_start = None
        _state.sleep_expected_wake = None
        _state = apply_deltas(_state, {"cortisol": 20, "norepinephrine": 12, "acetylcholine": -15})
        save_state(_state)
        await _update_presence(_state)
        messages = held
    elif _state.sleeping:
        _pending_wake[channel_id] = messages
        if _state.sleep_expected_wake:
            wake_str = time.strftime("%-I:%M %p", time.localtime(_state.sleep_expected_wake))
            notice = f"*[Mina is sleeping — she'll wake up around {wake_str}. Do you want to wake her up?]*"
        else:
            notice = "*[Mina is sleeping. Do you want to wake her up?]*"
        await channel.send(notice)
        return

    existing = _inflight.get(channel_id)
    if existing and not existing.done():
        rescued = _inflight_messages.pop(channel_id, [])
        existing.cancel()
        try:
            await existing
        except (asyncio.CancelledError, Exception):
            pass
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
    history = load_history()
    messages = []
    async for msg in channel.history(limit=SEED_MESSAGES, oldest_first=False):
        if msg.author.bot or not msg.content:
            continue
        messages.append(msg)
    messages.reverse()

    if not messages:
        return 0

    last_content = f"{messages[-1].author.display_name}: {messages[-1].content}"
    for entry in reversed(history):
        content = entry.get("content", "")
        if isinstance(content, list):
            content = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
        if entry.get("role") == "user" and content.endswith(messages[-1].content):
            return 0

    history.append({"role": "system", "content": "[DISCORD_SEED]"})
    for msg in messages:
        history.append({"role": "user", "content": f"{msg.author.display_name}: {msg.content}"})
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

# Register slash commands
from .discord_commands import setup as _setup_commands
_setup_commands(
    tree, client,
    pending=_pending,
    debounce_tasks=_debounce_tasks,
    inflight=_inflight,
    update_presence=_update_presence,
)


@client.event
async def on_ready():
    from ..infra import token_stats
    token_stats.reset()

    from src.config.config import load_config
    cfg = load_config()
    allowlist = [c.lstrip("#") for c in cfg.get("discord_channel_allowlist", [])]

    log("GATEWAY", f"Logged in as {client.user}")

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

    await tree.sync()
    log("GATEWAY", "Slash commands synced.")

    await _update_presence(load_state())
    _discord_send.register(_do_send)

    asyncio.create_task(bio_tick_loop())
    asyncio.create_task(_gateway_freetime_loop())
    asyncio.create_task(_followup_watcher())
    asyncio.create_task(_presence_loop())
    log("GATEWAY", "Bio tick, freetime, followup watcher, and presence loop started.")

    os.makedirs(_RUN_DIR, exist_ok=True)
    with open(_READY_FILE, "w") as f:
        f.write(str(time.time()))

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

    if seeded_total > 0:
        default_id = cfg.get("discord_default_channel_id")
        if default_id:
            ch = client.get_channel(int(default_id))
            if ch:
                asyncio.create_task(_run_catchup_turn(ch))

    log("GATEWAY", "Ready.")


async def _run_catchup_turn(channel: discord.abc.Messageable) -> None:
    await asyncio.sleep(1)
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
    if message.author == client.user or message.author.bot:
        return
    if not message.content and not message.attachments:
        return

    from src.config.config import load_config
    cfg = load_config()
    allowlist = [c.lstrip("#") for c in cfg.get("discord_channel_allowlist", [])]

    if allowlist and isinstance(message.channel, discord.TextChannel):
        if message.channel.name not in allowlist:
            return

    if isinstance(message.channel, discord.DMChannel):
        if not cfg.get("discord_enable_dms", True):
            return

    channel_id = message.channel.id
    _pending.setdefault(channel_id, []).append(message)

    with open(_HOME_CHANNEL_FILE, "w") as _f:
        _f.write(str(channel_id))

    existing = _debounce_tasks.get(channel_id)
    if existing and not existing.done():
        existing.cancel()

    task = asyncio.create_task(_debounce_fire(message.channel, channel_id))
    _debounce_tasks[channel_id] = task


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("ERROR: MINA_BOT_TOKEN not set.", file=sys.stderr)
        sys.exit(1)
    client.run(DISCORD_TOKEN)
