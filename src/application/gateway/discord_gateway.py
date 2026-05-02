"""
Discord gateway — primary entry point for Mina.

Run via supervisor.py (or directly for development):
    python -m src.application.gateway.discord_gateway
"""
import asyncio
import base64
import json
import logging
import os
import sys
import time

import aiohttp
import discord
from discord import app_commands
from dotenv import load_dotenv, find_dotenv

_DOTENV = find_dotenv(usecwd=True)
load_dotenv(_DOTENV)
_PROJECT_ROOT = os.path.dirname(_DOTENV)

from ..infra.log import log
from ..infra import discord_send as _discord_send
from ..infra.image_utils import normalise_image as _normalise_image
from src.config.config import RUN_DIR, REPO_ROOT

# Suppress noisy-but-harmless WebSocket transport errors on reconnect
class _SuppressResetError(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "Cannot write to closing transport" not in record.getMessage()

logging.getLogger("discord.client").addFilter(_SuppressResetError())
logging.getLogger("discord.gateway").addFilter(_SuppressResetError())

_RUN_DIR              = RUN_DIR
_READY_FILE           = os.path.join(_RUN_DIR, "ready")
_RESTART_PENDING_FILE = os.path.join(_RUN_DIR, "restart_pending.json")
_HOME_CHANNEL_FILE    = os.path.join(_RUN_DIR, "home_channel.txt")
_DISCORD_API          = "https://discord.com/api/v10"

DISCORD_TOKEN = os.getenv("MINA_BOT_TOKEN", "")
DEBOUNCE_DELAY = 0.1
CHUNK_SIZE = 1950

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


# ---------------------------------------------------------------------------
# Presence management
# ---------------------------------------------------------------------------

async def _update_presence() -> None:
    if not client.is_ready():
        return
    await client.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(type=discord.ActivityType.listening, name="you"),
    )


# ---------------------------------------------------------------------------
# Per-channel state
# ---------------------------------------------------------------------------

_pending: dict[int, list[discord.Message]] = {}
_debounce_tasks: dict[int, asyncio.Task] = {}
_inflight: dict[int, asyncio.Task] = {}
_inflight_messages: dict[int, list[discord.Message]] = {}


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


async def _send_with_retry(channel: discord.abc.Messageable, **kwargs) -> None:
    for attempt in range(4):
        try:
            await channel.send(**kwargs)
            return
        except discord.DiscordServerError as e:
            if attempt == 3:
                raise
            wait = 2 ** attempt
            log("GATEWAY/RETRY", f"send failed ({e}), retrying in {wait}s (attempt {attempt + 1}/4)")
            await asyncio.sleep(wait)


async def _deliver(channel: discord.abc.Messageable, reply: str, image_paths: list[str]) -> None:
    if reply:
        chunks = _chunk_text(reply)
        for chunk in chunks:
            await _send_with_retry(channel, content=chunk)
            if len(chunks) > 1:
                await asyncio.sleep(0.15)
    for path in image_paths:
        if os.path.exists(path):
            await _send_with_retry(channel, file=discord.File(path))


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
# Turn runner — response generation goes here
# ---------------------------------------------------------------------------

async def _run_turn(channel: discord.abc.Messageable, messages: list[discord.Message]) -> None:
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
                                images.append((b64, mime))
                except Exception as e:
                    log("VISION/ERROR", f"{att.filename}: {e}")

    try:
        async with channel.typing():
            raise NotImplementedError("run_turn not yet implemented")
    except asyncio.CancelledError:
        raise
    except NotImplementedError:
        raise
    except Exception as e:
        log("GATEWAY/ERROR", f"turn failed: {e}")
        return


# ---------------------------------------------------------------------------
# Debounce + inflight management
# ---------------------------------------------------------------------------

async def _debounce_fire(channel: discord.abc.Messageable, channel_id: int) -> None:
    await asyncio.sleep(DEBOUNCE_DELAY)

    messages = _pending.pop(channel_id, [])
    _debounce_tasks.pop(channel_id, None)

    if not messages:
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
# Bot setup
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

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

    log("GATEWAY", f"Logged in as {client.user}")

    await tree.sync()
    log("GATEWAY", "Slash commands synced.")

    await _update_presence()
    _discord_send.register(_do_send)

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

    log("GATEWAY", "Ready.")


@client.event
async def on_message(message: discord.Message) -> None:
    if message.author == client.user or message.author.bot:
        return
    if not message.content and not message.attachments:
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
