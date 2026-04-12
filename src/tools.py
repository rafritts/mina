"""
Mina's tools — biological actions, search, and image generation.

Biological tools: sleep, nap, do_action, message_user
Search tools:     web_search, x_search (via xAI Responses API)
Image:            generate_image (via ComfyUI)

`call_tool()` is the unified synchronous dispatcher.
`TOOLS` / `HEARTBEAT_TOOLS` are the OpenAI function-calling schemas offered to the LLM.
"""
import json
import os
import time
from typing import Any

from .config import OUTBOX_FILE, load_config
from .state import BiologicalState, save_state

_BASE_URL_SEARCH = os.getenv("BASE_URL", "https://api.x.ai/v1")
_API_KEY_SEARCH  = os.getenv("XAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
_SEARCH_MODEL    = "grok-3-latest"

_search_client = None


def _get_search_client():
    global _search_client
    if _search_client is None:
        from openai import OpenAI
        _search_client = OpenAI(api_key=_API_KEY_SEARCH, base_url=_BASE_URL_SEARCH)
    return _search_client


def _compression_factor() -> float:
    return float(load_config().get("time_compression_factor", 1.0))


def _is_sleep_window(cfg: dict) -> bool:
    """Return True if current local hour is within the configured sleep window."""
    start = int(cfg.get("sleep_window_start", 22))
    end   = int(cfg.get("sleep_window_end",   8))
    hour  = time.localtime().tm_hour
    # Window wraps midnight (e.g. 22→8): hour >= start OR hour < end
    if start > end:
        return hour >= start or hour < end
    return start <= hour < end


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

_BIOLOGICAL_TOOLS = [
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
            "name": "do_action",
            "description": "Do an action.",
            "parameters": {
                "type": "object",
                "properties": {
                    "activity": {
                        "type": "string",
                        "description": "What you're doing.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description.",
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
                        "description": "Image description (Danbooru-style tags). MINA.md appearance tags are prepended automatically for self-images.",
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

_SEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current information, news, topics you're curious about, "
                "anything you'd normally google. Returns a synthesized summary with sources."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "x_search",
            "description": (
                "Search X (Twitter) for recent posts. Use to find what people are talking "
                "about, trending memes, reactions, hot takes. Returns recent post content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                },
                "required": ["query"],
            },
        },
    },
]

# message_user is only available during freetime (she's already in a conversation for regular turns)
HEARTBEAT_TOOLS = _BIOLOGICAL_TOOLS + _SEARCH_TOOLS
_CONVERSATION_EXCLUDED = {"message_user"}
TOOLS = [t for t in HEARTBEAT_TOOLS if t["function"]["name"] not in _CONVERSATION_EXCLUDED]


# ---------------------------------------------------------------------------
# Biological tool handlers
# ---------------------------------------------------------------------------

def handle_sleep(args: dict, state: BiologicalState) -> tuple[str, BiologicalState]:
    cfg = load_config()
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
    cfg = load_config()
    if not cfg.get("naps_enabled", True):
        return "Napping isn't available right now.", state

    heartbeat_s = float(cfg.get("heartbeat_interval_seconds", 1800))
    compression = float(cfg.get("time_compression_factor", 1.0))

    state.sleeping = True
    state.sleep_start = time.time()
    state.sleep_expected_wake = time.time() + heartbeat_s

    sim_minutes = round(heartbeat_s * compression / 60.0)
    return f"You close your eyes for a short nap (~{sim_minutes} simulated minutes).", state


def handle_message_user(args: dict, state: BiologicalState) -> tuple[str, BiologicalState]:
    content = args.get("content", "").strip()
    if not content:
        return "[message_user: no content provided]", state
    os.makedirs(os.path.dirname(OUTBOX_FILE), exist_ok=True)
    with open(OUTBOX_FILE, "a") as f:
        f.write(json.dumps({"content": content, "timestamp": time.time()}) + "\n")
    return "Message queued.", state


def handle_do_action(args: dict, state: BiologicalState) -> tuple[str, BiologicalState, dict]:
    """
    Returns (message, state, pending_deltas).
    pending_deltas are evaluated by the encoder after the turn completes.
    """
    activity    = args.get("activity", "something")
    description = args.get("description", "")
    pending     = {"activity": activity, "description": description}
    return f"You {activity}. {description}".strip(), state, pending


# ---------------------------------------------------------------------------
# Search tool handlers
# ---------------------------------------------------------------------------

def handle_web_search(args: dict) -> str:
    query = args.get("query", "").strip()
    if not query:
        return "[web_search: no query provided]"
    try:
        response = _get_search_client().responses.create(
            model=_SEARCH_MODEL,
            tools=[{"type": "web_search"}],
            input=query,
        )
        return response.output_text or "[web_search: no results]"
    except Exception as e:
        return f"[web_search error: {e}]"


def handle_x_search(args: dict) -> str:
    query = args.get("query", "").strip()
    if not query:
        return "[x_search: no query provided]"
    try:
        response = _get_search_client().responses.create(
            model=_SEARCH_MODEL,
            tools=[{"type": "x_search"}],
            input=query,
        )
        return response.output_text or "[x_search: no results]"
    except Exception as e:
        return f"[x_search error: {e}]"


# ---------------------------------------------------------------------------
# Image generation
# ---------------------------------------------------------------------------

async def handle_generate_image(args: dict) -> str:
    """Generate an image via ComfyUI. Returns path or error string."""
    from skills.comfyui.comfyui_skill import generate_image
    from .hippocampus import read_identity

    prompt          = args.get("prompt", "")
    dimensions      = args.get("dimensions", "832x1216")
    filename        = args.get("filename", "mina")
    negative_prompt = args.get("negative_prompt", None)
    workflow        = args.get("workflow", "upscale")
    seed            = args.get("seed", None)

    mina_identity = read_identity("MINA.md")
    appearance_tags = ""
    if mina_identity:
        for line in mina_identity.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("prompt:"):
                appearance_tags = stripped[len("prompt:"):].strip()
                break
    if appearance_tags and appearance_tags not in prompt:
        prompt = f"{appearance_tags}, {prompt}"

    from .log import log
    log("COMFY", f"workflow={workflow} dimensions={dimensions} seed={seed}")
    log("COMFY", f"prompt={prompt[:200]}")
    if negative_prompt:
        log("COMFY", f"negative={negative_prompt[:120]}")

    try:
        path = await generate_image(
            prompt=prompt,
            dimensions=dimensions,
            filename=filename,
            negative_prompt=negative_prompt,
            seed=seed,
            workflow=workflow,
        )
        log("COMFY", f"output={path or 'none'}")
        return path or ""
    except Exception as e:
        log("COMFY/ERROR", str(e))
        return f"[Image generation failed: {e}]"


# ---------------------------------------------------------------------------
# Unified dispatcher
# ---------------------------------------------------------------------------

def call_tool(name: str, args: dict, state: BiologicalState) -> tuple[str, BiologicalState, dict]:
    """
    Synchronous dispatcher for all tools.
    Returns (result_str, updated_state, extra_data).
    extra_data is non-empty only for do_action (contains pending activity for encoder).
    """
    if name == "sleep":
        msg, state = handle_sleep(args, state)
        return msg, state, {}
    elif name == "nap":
        msg, state = handle_nap(args, state)
        return msg, state, {}
    elif name == "do_action":
        msg, state, pending = handle_do_action(args, state)
        return msg, state, pending
    elif name == "message_user":
        msg, state = handle_message_user(args, state)
        return msg, state, {}
    elif name == "web_search":
        return handle_web_search(args), state, {}
    elif name == "x_search":
        return handle_x_search(args), state, {}
    else:
        return f"[Unknown tool: {name}]", state, {}
