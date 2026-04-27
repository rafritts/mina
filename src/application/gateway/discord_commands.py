"""
Discord slash commands — registered via setup(tree, client_ref, ...).

All commands are defined inside setup() so they close over the shared gateway
state (pending/inflight dicts, update_presence callable) passed at startup.
"""
import asyncio
import datetime
import json
import os
import tempfile
import time

import aiohttp
import discord
from discord import app_commands

from src.config.config import PAUSED_FLAG, RUN_DIR, REPO_ROOT
from src.brain.cortex.cortex import load_history, save_history, HISTORY_MAX
from src.brain.brainstem.state import load_and_advance, save_state, load_state, apply_deltas, derived
from src.brain.hippocampus.hippocampus import rag_wipe, kag_apply_replacements, rag_apply_replacements
from ..infra.text_filter import apply_replacements, llm_derive_replacements
from .discord_ui import _AvatarConfirmView, _DISCORD_API

_CONFIG_FILE    = os.path.join(REPO_ROOT, "config.json")
_DEFAULT_AVATAR = os.path.join(REPO_ROOT, "avatar.png")
_STOPPED_FLAG         = os.path.join(RUN_DIR, ".stopped")
_RESTART_PENDING_FILE = os.path.join(RUN_DIR, "restart_pending.json")


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _wipe_user_data() -> list[str]:
    import glob as _glob
    wiped = []
    conv_daily_files = _glob.glob(os.path.join(RUN_DIR, "conversation-*.jsonl"))
    spec32_paths = [os.path.relpath(p, REPO_ROOT).replace(os.sep, "/") for p in conv_daily_files]

    for rel_path in [
        "run/conversation.json",
        "run/conversation.json.archived",
        "run/decoder_window.json",
        "run/decoder_history.jsonl",
        "run/bio_snapshots.jsonl",
        "run/last_search.json",
        "run/consolidation_state.json",
        "run/bio_history.jsonl",
        "run/events.jsonl",
        "run/token_stats.json",
        "run/followup_queue.json",
        "run/sliding_seq.json",
    ] + spec32_paths:
        dst = os.path.join(REPO_ROOT, rel_path)
        if os.path.exists(dst):
            os.remove(dst)
            wiped.append(rel_path)

    kag_dir = os.path.join(REPO_ROOT, "memory", "kag")
    if os.path.exists(kag_dir):
        for root, dirs, files in os.walk(kag_dir):
            for fname in files:
                full = os.path.join(root, fname)
                os.remove(full)
                wiped.append(os.path.relpath(full, REPO_ROOT).replace(os.sep, "/"))
    os.makedirs(kag_dir, exist_ok=True)

    try:
        rag_wipe()
        wiped.append("memory/rag/ (RAG wiped)")
    except Exception as e:
        wiped.append(f"memory/rag/ (wipe failed: {e})")

    return wiped


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
        save_history([])
        from src.application.infra import token_stats
        token_stats.reset()
        await interaction.response.send_message("History cleared.", ephemeral=True)

    @tree.command(name="reset", description="Wipe Mina's memory, state, and history.")
    async def cmd_reset(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            wiped = _wipe_user_data()
            os.makedirs(RUN_DIR, exist_ok=True)
            with open(_RESTART_PENDING_FILE, "w") as f:
                json.dump({"token": interaction.token, "application_id": interaction.application_id}, f)
            await interaction.followup.send(
                f"Reset complete. Restarting...\nWiped: {', '.join(wiped)}", ephemeral=True
            )
            os._exit(42)
        except Exception as e:
            await interaction.followup.send(f"Reset failed: {e}", ephemeral=True)

    @tree.command(name="factory-reset", description="Nuclear reset: wipe everything including biomarkers.")
    async def cmd_factory_reset(interaction: discord.Interaction):
        from src.brain.brainstem.state import BiologicalState
        await interaction.response.defer(ephemeral=True)
        try:
            wiped = _wipe_user_data()
            save_state(BiologicalState())
            wiped.append("state.json (biomarkers reset to defaults)")
            os.makedirs(RUN_DIR, exist_ok=True)
            with open(_RESTART_PENDING_FILE, "w") as f:
                json.dump({"token": interaction.token, "application_id": interaction.application_id}, f)
            await interaction.followup.send(
                f"Factory reset complete. Restarting...\nWiped: {', '.join(wiped)}", ephemeral=True
            )
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
        from src.application.infra.events import read_events
        all_events = read_events(limit=300)
        tool_events = [e for e in all_events if e.get("type") == "tool"][:n]
        if not tool_events:
            await interaction.response.send_message("No tool calls recorded yet.", ephemeral=True)
            return

        CHEM_SHORT = {
            "cortisol": "cort", "norepinephrine": "norepi", "dopamine": "dopa",
            "serotonin": "sero", "oxytocin": "oxy", "endorphins": "endo",
            "acetylcholine": "ach", "melatonin": "mela", "glucose": "gluc",
            "hydration": "hydr", "sleep_pressure": "sleep",
        }
        lines = []
        for e in tool_events:
            tool    = e.get("tool", "?")
            args    = e.get("args", {})
            result  = e.get("result", "")
            deltas  = e.get("deltas", {})
            source  = e.get("source", "")
            ts      = e.get("ts", 0)

            delta = time.time() - ts
            if delta < 60:     age = "just now"
            elif delta < 3600: age = f"{int(delta/60)}m ago"
            elif delta < 86400: age = f"{int(delta/3600)}h ago"
            else:              age = f"{int(delta/86400)}d ago"

            if tool == "do_action":
                summary = args.get("activity", "")
            elif tool == "sleep":
                summary = f"{args.get('duration_hours', '?')}h"
            elif tool in ("web_search", "x_search"):
                summary = args.get("query", "")
            else:
                summary = ", ".join(f"{k}={v}" for k, v in args.items()) if args else ""

            delta_str = ""
            if deltas:
                parts = []
                for k, v in deltas.items():
                    short = CHEM_SHORT.get(k, k)
                    sign = "+" if v > 0 else ""
                    parts.append(f"{short}{sign}{v:.1f}")
                delta_str = f" `{' '.join(parts)}`"

            src_tag = f" _{source}_" if source else ""
            lines.append(f"**{tool}** {summary}{src_tag} · {age}{delta_str}")
            if result:
                lines.append(f"  ↳ {result[:120]}")

        await interaction.response.send_message("\n".join(lines)[:1900], ephemeral=True)

    @tree.command(name="state", description="Show Mina's current biological state.")
    async def cmd_state(interaction: discord.Interaction):
        s = load_and_advance()
        d = derived(s)
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
        from src.engine.chem.units import get_label
        s = load_and_advance()
        d = derived(s)
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
            from src.engine.neuro.substances import SUBSTANCE_DEFS
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
        await interaction.response.send_message(f"Time compression set to {factor}x.", ephemeral=True)

    @tree.command(name="sleep", description="Put Mina to sleep.")
    @app_commands.describe(hours="How many simulated hours to sleep")
    async def cmd_sleep(interaction: discord.Interaction, hours: float = 8.0):
        from src.brain.cortex.tools import handle_sleep
        s = load_and_advance()
        _, s = handle_sleep({"duration_hours": hours}, s)
        save_state(s)
        await update_presence(s)
        await interaction.response.send_message(
            f"Mina is going to sleep for {hours:.1f} simulated hours.", ephemeral=True
        )

    @tree.command(name="wake", description="Force-wake Mina (she'll be groggy).")
    async def cmd_wake(interaction: discord.Interaction):
        s = load_and_advance()
        s.sleeping = False
        s.sleep_start = None
        s.sleep_expected_wake = None
        s = apply_deltas(s, {"cortisol": 20, "norepinephrine": 12, "acetylcholine": -15})
        save_state(s)
        await update_presence(s)
        await interaction.response.send_message("Mina has been woken up.", ephemeral=True)

    @tree.command(name="heartbeat", description="Manually trigger one heartbeat cycle.")
    async def cmd_heartbeat(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from src.brain.subconscious.freetime import run_freetime
        try:
            await run_freetime()
            await interaction.followup.send("Heartbeat complete.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Heartbeat error: {e}", ephemeral=True)

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

    @tree.command(name="pause", description="Pause biological updating (no time decay, no heartbeat).")
    async def cmd_pause(interaction: discord.Interaction):
        os.makedirs(RUN_DIR, exist_ok=True)
        open(PAUSED_FLAG, "w").close()
        await interaction.response.send_message("Biological updates paused.", ephemeral=True)

    @tree.command(name="resume", description="Resume biological updating.")
    async def cmd_resume(interaction: discord.Interaction):
        try:
            os.remove(PAUSED_FLAG)
        except FileNotFoundError:
            pass
        await interaction.response.send_message("Biological updates resumed.", ephemeral=True)

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

    @tree.command(name="context", description="Show Mina's context window, bio state, and config.")
    async def cmd_context(interaction: discord.Interaction):
        from src.brain.hippocampus.hippocampus import read_kag
        cfg = _load_config()
        s = load_state()
        d = derived(s)
        so = d["second_order"]
        to = d["third_order"]

        history = load_history()
        total_msgs = len(history)
        role_counts: dict[str, int] = {}
        for m in history:
            role = m.get("role", "?")
            role_counts[role] = role_counts.get(role, 0) + 1
        pct = (total_msgs / HISTORY_MAX * 100) if HISTORY_MAX else 0
        bar_filled = min(20, int(pct / 5))
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        role_str = "  ".join(f"{r}: {c}" for r, c in sorted(role_counts.items()))

        reflection_text = read_kag("REFLECTION.md") or ""
        reflection_words = len(reflection_text.split()) if reflection_text else 0
        reflection_preview = (
            reflection_text[:120].replace("\n", " ") + ("…" if len(reflection_text) > 120 else "")
            if reflection_text else "(empty)"
        )

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
            f"Paused: {os.path.exists(PAUSED_FLAG)}",
            "```",
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @tree.command(name="fix-false-positive", description="Scrub age-ambiguous language triggering Grok's CSAM filter from history, KAG, and RAG.")
    async def cmd_fix_false_positive(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            history = load_history()
            replacements = await asyncio.to_thread(llm_derive_replacements, history)
            if not replacements:
                await interaction.followup.send("LLM found nothing to replace.", ephemeral=True)
                return

            def _fix_content(content):
                if isinstance(content, str):
                    fixed = apply_replacements(content, replacements)
                    return fixed, fixed != content
                if isinstance(content, list):
                    changed = False
                    result = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            fixed = apply_replacements(item["text"], replacements)
                            changed = changed or fixed != item["text"]
                            result.append({**item, "text": fixed})
                        else:
                            result.append(item)
                    return result, changed
                return content, False

            history_hits = 0
            new_history = []
            for entry in history:
                content, changed = _fix_content(entry.get("content", ""))
                if changed:
                    history_hits += 1
                new_history.append({**entry, "content": content})
            if history_hits:
                save_history(new_history)

            kag_modified = await asyncio.to_thread(kag_apply_replacements, replacements)
            rag_hits = await asyncio.to_thread(rag_apply_replacements, replacements)

            repl_summary = ", ".join(f'"{r["find"]}" → "{r["replace"]}"' for r in replacements)
            parts = [
                f"Replacements derived: {repl_summary}",
                f"History messages patched: {history_hits}",
                f"KAG files patched: {', '.join(kag_modified)}" if kag_modified else "KAG files: none needed patching",
                f"RAG entries re-embedded: {rag_hits}",
            ]
            await interaction.followup.send("\n".join(parts), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"fix-false-positive failed: {e}", ephemeral=True)
