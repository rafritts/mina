"""
Discord UI components — avatar confirmation view and avatar REST call.
"""
import base64
import mimetypes
import os

import aiohttp
import discord

_DISCORD_API = "https://discord.com/api/v10"


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

    return "Avatar updated."
