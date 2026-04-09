"""
Mina's biological tools — sleep, eat, drink, rest, do — plus image generation.

Each tool modifies state.json directly. The subconscious applies activity-based
deltas for the `do` tool after the heartbeat turn completes.
"""
import json
import os
import random
import time
from typing import Any

from state import BiologicalState, apply_deltas, load_state, save_state, _clamp
from tools_search import SEARCH_TOOLS, call_search_tool

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_PROJECT_ROOT, "config.json")
_OUTBOX_FILE = os.path.join(_PROJECT_ROOT, "run", "outbox.jsonl")


def _load_config() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _compression_factor() -> float:
    return float(_load_config().get("time_compression_factor", 1.0))


def _is_sleep_window(cfg: dict) -> bool:
    """Return True if current local hour is within the configured sleep window."""
    start = int(cfg.get("sleep_window_start", 22))
    end = int(cfg.get("sleep_window_end", 8))
    hour = time.localtime().tm_hour
    # Window wraps midnight (e.g. 22 → 8): allowed if hour >= start OR hour < end
    # Same-day window (e.g. 14 → 17): allowed if start <= hour < end
    if start > end:
        return hour >= start or hour < end
    return start <= hour < end


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "sleep",
            "description": (
                "Go to sleep for the night. Only works during your sleep window "
                "(configured hours — outside that window this will be blocked). "
                "Use nap if you need rest outside those hours."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "duration_hours": {
                        "type": "number",
                        "description": "How long you want to sleep in simulated hours (suggestion only — actual duration may vary).",
                    }
                },
                "required": ["duration_hours"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nap",
            "description": (
                "Take a short nap to knock down sleep pressure. "
                "Lasts one heartbeat cycle. Available any time if naps are enabled."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "eat",
            "description": "Eat something.",
            "parameters": {
                "type": "object",
                "properties": {
                    "what": {
                        "type": "string",
                        "description": "What you're eating.",
                    }
                },
                "required": ["what"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drink",
            "description": "Drink something.",
            "parameters": {
                "type": "object",
                "properties": {
                    "what": {
                        "type": "string",
                        "description": "What you're drinking.",
                    }
                },
                "required": ["what"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rest",
            "description": "Rest for a while without fully sleeping.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "do",
            "description": "Do something during your free time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "activity": {
                        "type": "string",
                        "description": "What you're doing (e.g. 'read', 'play a game', 'take a shower')",
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of how you're engaging with it.",
                    },
                },
                "required": ["activity", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "message_user",
            "description": "Send a message to the user in Discord. Use this when you want to reach out — you have something on your mind, you want company, you noticed something, whatever. You initiate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "What you want to say.",
                    }
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Generate an image via ComfyUI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Image description (Danbooru-style tags). APPEARANCE.md tags are prepended automatically for self-images.",
                    },
                    "dimensions": {
                        "type": "string",
                        "description": "WIDTHxHEIGHT e.g. 832x1216",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Output filename (no extension)",
                    },
                    "negative_prompt": {
                        "type": "string",
                        "description": "What to avoid in the image.",
                    },
                    "workflow": {
                        "type": "string",
                        "enum": ["upscale", "no_upscale"],
                        "description": "upscale (~60s, higher quality) or no_upscale (~20s, faster)",
                    },
                    "seed": {
                        "type": "integer",
                        "description": "Random seed. 0 or omit for random.",
                    },
                },
                "required": ["prompt"],
            },
        },
    },
]


# Add search tools to all contexts — she can search during conversation and free time
TOOLS = TOOLS + SEARCH_TOOLS

# During regular turns, message_user is not offered (she's already in a conversation).
# During heartbeat free-time, all tools including message_user are available.
HEARTBEAT_TOOLS = TOOLS  # message_user is already in TOOLS; filter it out for main turns below
TOOLS = [t for t in TOOLS if t["function"]["name"] != "message_user"]


# ---------------------------------------------------------------------------
# Tool dispatchers
# ---------------------------------------------------------------------------

def handle_sleep(args: dict, state: BiologicalState) -> tuple[str, BiologicalState]:
    """Set sleeping state. Blocked outside the configured sleep window."""
    cfg = _load_config()
    if not _is_sleep_window(cfg):
        if cfg.get("naps_enabled", True):
            return (
                "It's outside your sleep window — full sleep isn't available right now. "
                "You can take a nap if you need rest.",
                state,
            )
        return "It's outside your sleep window — you can't sleep right now.", state

    duration_hours = float(args.get("duration_hours", 8.0))
    compression = _compression_factor()
    real_seconds = (duration_hours * 3600) / compression

    state.sleeping = True
    state.sleep_start = time.time()
    state.sleep_expected_wake = time.time() + real_seconds

    return (
        f"You drift off to sleep. Expected wake in {duration_hours:.1f} simulated hours.",
        state,
    )


def handle_nap(args: dict, state: BiologicalState) -> tuple[str, BiologicalState]:
    """Take a short nap lasting one heartbeat interval. Bypasses the sleep window."""
    cfg = _load_config()
    if not cfg.get("naps_enabled", True):
        return "Napping isn't available right now.", state

    heartbeat_s = float(cfg.get("heartbeat_interval_seconds", 1800))
    compression = float(cfg.get("time_compression_factor", 1.0))

    state.sleeping = True
    state.sleep_start = time.time()
    state.sleep_expected_wake = time.time() + heartbeat_s  # one real heartbeat

    sim_minutes = round(heartbeat_s * compression / 60.0)
    return f"You close your eyes for a short nap (~{sim_minutes} simulated minutes).", state


def handle_eat(args: dict, state: BiologicalState) -> tuple[str, BiologicalState]:
    what = args.get("what", "something")

    glucose_gain = random.uniform(25, 40)
    serotonin_gain = random.uniform(3, 8)
    cortisol_change = -random.uniform(5, 10) if state.glucose < 40 else -random.uniform(0, 3)

    deltas = {
        "glucose": glucose_gain,
        "serotonin": serotonin_gain,
        "cortisol": cortisol_change,
    }

    # Comfort foods get an endorphin bump
    comfort_words = {"chocolate", "cheese", "pasta", "bread", "cake", "soup", "pizza", "cookie"}
    if any(w in what.lower() for w in comfort_words):
        deltas["endorphins"] = random.uniform(5, 12)

    state = apply_deltas(state, deltas)
    return f"You eat {what}.", state


def handle_drink(args: dict, state: BiologicalState) -> tuple[str, BiologicalState]:
    what = args.get("what", "water")
    what_lower = what.lower()

    deltas: dict[str, float] = {}

    caffeine_words = {"coffee", "tea", "espresso", "latte", "cappuccino", "energy drink", "matcha"}
    alcohol_words = {"beer", "wine", "whiskey", "vodka", "gin", "rum", "alcohol", "drink", "cocktail"}

    if any(w in what_lower for w in caffeine_words):
        deltas["norepinephrine"] = random.uniform(15, 25)
        deltas["sleep_pressure"] = -random.uniform(8, 12)  # temporary suppression
        deltas["hydration"] = random.uniform(3, 8)
        tol = state.tolerance.get("caffeine", 0.0)
        state.tolerance["caffeine"] = min(1.0, tol + 0.05)

    elif any(w in what_lower for w in alcohol_words):
        tol = state.tolerance.get("alcohol", 0.0)
        effective = 1.0 - tol
        deltas["cortisol"] = -random.uniform(12, 20) * effective
        deltas["serotonin"] = random.uniform(5, 10) * effective
        deltas["acetylcholine"] = -random.uniform(8, 15) * effective
        deltas["norepinephrine"] = -random.uniform(5, 10) * effective
        deltas["hydration"] = -random.uniform(5, 10)  # dehydrating
        state.tolerance["alcohol"] = min(1.0, tol + 0.05)

    else:
        # Water or other non-caffeinated, non-alcoholic
        deltas["hydration"] = random.uniform(20, 28)

    state = apply_deltas(state, deltas)
    return f"You drink {what}.", state


def handle_rest(args: dict, state: BiologicalState) -> tuple[str, BiologicalState]:
    deltas = {
        "cortisol": -random.uniform(8, 14),
        "sleep_pressure": -random.uniform(3, 6),
        "endorphins": random.uniform(3, 6),
    }
    state = apply_deltas(state, deltas)
    return "You rest for a while.", state


def handle_message_user(args: dict, state: BiologicalState) -> tuple[str, BiologicalState]:
    """Queue a message for delivery to the Discord channel."""
    content = args.get("content", "").strip()
    if not content:
        return "[message_user: no content provided]", state
    os.makedirs(os.path.dirname(_OUTBOX_FILE), exist_ok=True)
    with open(_OUTBOX_FILE, "a") as f:
        f.write(json.dumps({"content": content, "timestamp": time.time()}) + "\n")
    return f"Message queued.", state


def handle_do(args: dict, state: BiologicalState) -> tuple[str, BiologicalState, dict]:
    """
    Do tool — returns (message, state, pending_deltas).
    pending_deltas are returned to the caller (heartbeat/main) for the subconscious
    to evaluate and apply after the turn completes.
    """
    activity = args.get("activity", "something")
    description = args.get("description", "")
    # Actual deltas will be determined by the subconscious after the turn.
    # We return the activity info for the subconscious to evaluate.
    pending = {"activity": activity, "description": description}
    return f"You {activity}. {description}".strip(), state, pending


async def handle_generate_image(args: dict) -> str:
    """Generate an image via ComfyUI. Returns path or empty string."""
    from skills.comfyui.comfyui_skill import generate_image

    prompt = args.get("prompt", "")
    dimensions = args.get("dimensions", "832x1216")
    filename = args.get("filename", "mina")
    negative_prompt = args.get("negative_prompt", None)
    workflow = args.get("workflow", "upscale")
    seed = args.get("seed", None)

    # Prepend appearance tags for any image (Mina is always in the frame unless overridden)
    from memory import read_identity
    appearance = read_identity("APPEARANCE.md")
    appearance_tags = ""
    if appearance:
        # Extract the "prompt:" line from the ComfyUI Generation Tags section
        for line in appearance.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("prompt:"):
                appearance_tags = stripped[len("prompt:"):].strip()
                break
    if appearance_tags and appearance_tags not in prompt:
        prompt = f"{appearance_tags}, {prompt}"

    print(f"  [comfy] workflow={workflow} dimensions={dimensions} seed={seed}")
    print(f"  [comfy] prompt={prompt[:200]}")
    if negative_prompt:
        print(f"  [comfy] negative={negative_prompt[:120]}")

    try:
        path = await generate_image(
            prompt=prompt,
            dimensions=dimensions,
            filename=filename,
            negative_prompt=negative_prompt,
            seed=seed,
            workflow=workflow,
        )
        print(f"  [comfy] output={path or 'none'}")
        return path or ""
    except Exception as e:
        print(f"  [comfy] ERROR: {e}")
        return f"[Image generation failed: {e}]"


def call_tool(name: str, args: dict, state: BiologicalState) -> tuple[str, BiologicalState, dict]:
    """
    Synchronous dispatcher for biological tools.
    Returns (result_str, updated_state, extra_data).
    extra_data is non-empty only for `do` (contains pending activity for subconscious).
    """
    if name == "sleep":
        msg, state = handle_sleep(args, state)
        return msg, state, {}
    elif name == "nap":
        msg, state = handle_nap(args, state)
        return msg, state, {}
    elif name == "eat":
        msg, state = handle_eat(args, state)
        return msg, state, {}
    elif name == "drink":
        msg, state = handle_drink(args, state)
        return msg, state, {}
    elif name == "rest":
        msg, state = handle_rest(args, state)
        return msg, state, {}
    elif name == "do":
        msg, state, pending = handle_do(args, state)
        return msg, state, pending
    elif name == "message_user":
        msg, state = handle_message_user(args, state)
        return msg, state, {}
    elif name in ("web_search", "x_search"):
        result = call_search_tool(name, args)
        return result, state, {}
    else:
        return f"[Unknown tool: {name}]", state, {}
