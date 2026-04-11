"""
CLI entry point — development and testing only.

The primary interface is Discord (discord_gateway.py). This CLI is for local testing.
`run_turn()` and all core turn logic live in cortex.py.
"""
import asyncio
import os
import sys

from config import PAUSED_FLAG, load_config
from cortex import run_turn
from heartbeat import bio_tick_loop
from freetime import run_freetime


async def _freetime_loop() -> None:
    while True:
        cfg = load_config()
        interval = int(cfg.get("heartbeat_interval_seconds", 1800))
        await asyncio.sleep(interval)
        if os.path.exists(PAUSED_FLAG):
            print("[FREETIME] Paused — skipping.")
            continue
        print(f"\n[FREETIME] Firing (interval={interval}s)...")
        try:
            await run_freetime()
        except Exception as e:
            print(f"[FREETIME ERROR] {e}")


def _cli_run_command(cmd: str) -> bool:
    """Handle a CLI slash command. Returns True if handled."""
    from state import load_and_advance, log_state

    parts = cmd.strip().split()
    name  = parts[0].lower()

    if name == "/reset":
        from discord_gateway import _wipe_user_data
        wiped = _wipe_user_data()
        print(f"Reset complete. Wiped: {', '.join(wiped)}")
        return True

    if name == "/factory-reset":
        confirm = input("Wipes everything including biomarkers. Type YES to confirm: ").strip()
        if confirm == "YES":
            from discord_gateway import _wipe_user_data
            from state import BiologicalState, save_state
            wiped = _wipe_user_data()
            save_state(BiologicalState())
            wiped.append("state.json (biomarkers reset to defaults)")
            print(f"Factory reset complete. Wiped: {', '.join(wiped)}")
        else:
            print("Cancelled.")
        return True

    if name == "/state":
        state = load_and_advance()
        log_state(state)
        return True

    if name in {"/help", "/?"}:
        print(
            "Commands:\n"
            "  /state           — show current biological state\n"
            "  /reset           — wipe relationship/RAG/knowledge/history; keep biomarkers + identity\n"
            "  /factory-reset   — same as /reset + reset biomarkers; identity (MINA.md/APPEARANCE.md) always preserved\n"
            "  exit / quit      — exit"
        )
        return True

    return False


async def _cli_main() -> None:
    cfg = load_config()
    print(f"Mina CLI — time_compression={cfg.get('time_compression_factor', 1.0)}x  (type /help for commands)\n")

    asyncio.create_task(bio_tick_loop())
    asyncio.create_task(_freetime_loop())

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            sys.exit(0)

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            sys.exit(0)
        if user_input.startswith("/"):
            if _cli_run_command(user_input):
                continue

        reply, image_paths = await run_turn(user_input, username="user")
        print(f"\nMina: {reply}\n")
        for path in image_paths:
            print(f"  [image] {path}")


if __name__ == "__main__":
    asyncio.run(_cli_main())
