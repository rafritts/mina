"""
Discord slash commands — registered via setup(tree, client_ref, ...).
"""
import asyncio
import datetime
import json
import os
import tempfile

import aiohttp
import discord
from discord import app_commands

from src.config.config import RUN_DIR, REPO_ROOT, get_conversation_file
from src.application.infra import token_stats

_DEFAULT_AVATAR       = os.path.join(REPO_ROOT, "avatar.png")
_STOPPED_FLAG         = os.path.join(RUN_DIR, ".stopped")
_RESTART_PENDING_FILE = os.path.join(RUN_DIR, "restart_pending.json")


def setup(
    tree: app_commands.CommandTree,
    client_ref: discord.Client,
    *,
    pending: dict,
    debounce_tasks: dict,
    inflight: dict,
    update_presence,
) -> None:
    """Register all slash commands on tree. Call once after client + tree are created."""

    @tree.command(name="new", description="Clear conversation history and start fresh.")
    async def cmd_new(interaction: discord.Interaction):
        conv_file = get_conversation_file()
        if os.path.exists(conv_file):
            os.remove(conv_file)
        token_stats.reset()
        await interaction.response.send_message("History cleared.", ephemeral=True)

    @tree.command(name="history", description="Show recent conversation history.")
    @app_commands.describe(n="Number of entries to show (default 10)")
    async def cmd_history(interaction: discord.Interaction, n: int = 10):
        conv_file = get_conversation_file()
        entries = []
        try:
            with open(conv_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except FileNotFoundError:
            pass

        entries = [e for e in entries if e.get("role") in ("user", "assistant")][-n:]
        if not entries:
            await interaction.response.send_message("No history yet.", ephemeral=True)
            return
        lines = []
        for e in entries:
            role = "Mina" if e["role"] == "assistant" else "User"
            content = e.get("content", "")
            if isinstance(content, list):
                content = next((b["text"] for b in content if b.get("type") == "text"), "")
            lines.append(f"**{role}:** {str(content)[:200]}")
        await interaction.response.send_message("\n".join(lines)[:1900], ephemeral=True)

    @tree.command(name="cancel", description="Cancel current turn in this channel.")
    async def cmd_cancel(interaction: discord.Interaction):
        channel_id = interaction.channel_id
        stopped = False

        dbt = debounce_tasks.get(channel_id)
        if dbt and not dbt.done():
            dbt.cancel()
            pending.pop(channel_id, None)
            debounce_tasks.pop(channel_id, None)
            stopped = True

        inf = inflight.get(channel_id)
        if inf and not inf.done():
            inf.cancel()
            stopped = True

        await interaction.response.send_message(
            "Cancelled." if stopped else "Nothing to cancel.", ephemeral=True
        )

    @tree.command(name="cancel-all", description="Cancel all running turns.")
    async def cmd_cancel_all(interaction: discord.Interaction):
        count = 0
        for task in list(debounce_tasks.values()):
            if not task.done():
                task.cancel()
                count += 1
        debounce_tasks.clear()
        pending.clear()

        for task in list(inflight.values()):
            if not task.done():
                task.cancel()
                count += 1

        await interaction.response.send_message(
            f"Cancelled {count} task(s)." if count else "Nothing to cancel.", ephemeral=True
        )

    @tree.command(name="set-avatar", description="Set Mina's avatar. Attach an image, or leave blank to use avatar.png.")
    @app_commands.describe(image="Image to upload (png, jpg, gif). Leave blank to use avatar.png in the repo.")
    async def cmd_set_avatar(interaction: discord.Interaction, image: discord.Attachment = None):
        from src.application.gateway.discord_ui import _AvatarConfirmView
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
                    "No `avatar.png` found in the repo root. Attach an image instead.", ephemeral=True
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

    @tree.command(name="stop", description="Stop Mina (supervisor will not restart until 'mina unstop').")
    async def cmd_stop(interaction: discord.Interaction):
        try:
            await interaction.response.send_message(
                "Stopping. Run `mina unstop` then `mina start` to bring her back.", ephemeral=True
            )
        except Exception:
            pass
        os.makedirs(RUN_DIR, exist_ok=True)
        open(_STOPPED_FLAG, "w").close()
        os._exit(0)

    @tree.command(name="restart", description="Restart Mina.")
    async def cmd_restart(interaction: discord.Interaction):
        try:
            await interaction.response.send_message(
                "Restarting... this message will update when she's back.", ephemeral=True
            )
            os.makedirs(RUN_DIR, exist_ok=True)
            with open(_RESTART_PENDING_FILE, "w") as f:
                json.dump({"token": interaction.token, "application_id": interaction.application_id}, f)
        except Exception:
            pass
        os._exit(42)

    @tree.command(name="clean", description="Delete Mina's messages in this channel.")
    @app_commands.describe(n="Number of messages to delete (default: all)")
    async def cmd_clean(interaction: discord.Interaction, n: int = 0):
        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel or await client_ref.fetch_channel(interaction.channel_id)

        scan_limit = (n * 5) if n > 0 else 500
        deleted_count = 0
        cutoff = discord.utils.utcnow() - datetime.timedelta(days=14)
        bulk_batch: list[discord.Message] = []
        old_msgs: list[discord.Message] = []

        try:
            async for msg in channel.history(limit=scan_limit, oldest_first=False):
                if msg.author != client_ref.user:
                    continue
                if msg.created_at > cutoff:
                    bulk_batch.append(msg)
                else:
                    old_msgs.append(msg)
                if n > 0 and (len(bulk_batch) + len(old_msgs)) >= n:
                    break

            can_bulk = hasattr(channel, "delete_messages")
            for i in range(0, len(bulk_batch), 100):
                chunk = bulk_batch[i:i + 100]
                if can_bulk:
                    await channel.delete_messages(chunk)
                    deleted_count += len(chunk)
                else:
                    old_msgs = chunk + old_msgs

            for msg in old_msgs:
                await msg.delete()
                deleted_count += 1
                await asyncio.sleep(1.1)

        except discord.HTTPException as e:
            await interaction.followup.send(f"Deleted {deleted_count} before error: {e}", ephemeral=True)
            return

        await interaction.followup.send(f"Deleted {deleted_count} message(s).", ephemeral=True)
