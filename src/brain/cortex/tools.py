"""
Mina's tools — biological actions and search.

Biological tools: sleep, nap, do_action, message_user
Search tools:     web_search, x_search (via xAI Responses API)

`call_tool()` is the unified synchronous dispatcher.
`TOOLS` / `HEARTBEAT_TOOLS` are the OpenAI function-calling schemas offered to the LLM.
"""
import json
import os
import time
from typing import Any

from src.config.config import FOLLOWUP_QUEUE_FILE, load_config
from src.application.infra import discord_send as _discord_send
from src.brain.brainstem.state import BiologicalState, save_state

_BASE_URL_SEARCH = os.getenv("BASE_URL", "https://api.x.ai/v1")
_API_KEY_SEARCH  = os.getenv("XAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))

# Web/X search use the same model as the main conversation so the setting stays in sync.
# The Responses API requires a model that supports server-side tools (web_search, x_search).
from src.config.config import MODEL as _MAIN_MODEL
_SEARCH_MODEL = os.getenv("SEARCH_MODEL", _MAIN_MODEL)

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


def _is_nap_blackout(cfg: dict) -> bool:
    """Return True if we're within nap_blackout_hours of the sleep window start.

    Prevents naps that would blunt sleep pressure right before bedtime.
    Default blackout: 4 hours. Set nap_blackout_hours=0 to disable.
    """
    blackout_hours = float(cfg.get("nap_blackout_hours", 4))
    if blackout_hours <= 0:
        return False
    start = int(cfg.get("sleep_window_start", 22))
    now = time.localtime()
    # Convert both to minutes-since-midnight for easy arithmetic
    now_min   = now.tm_hour * 60 + now.tm_min
    start_min = start * 60
    # Minutes until sleep window (wrapping midnight)
    delta_min = (start_min - now_min) % (24 * 60)
    return delta_min <= blackout_hours * 60


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
                "Lasts one heartbeat cycle. Blocked within a few hours of your sleep window "
                "— napping too close to bedtime will make it harder to fall asleep."
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
]

_FOLLOWUP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "schedule_followup",
            "description": (
                "Schedule a deferred response. You will be reinvoked at the specified time "
                "with only the context you provide — no conversation history. Use this when "
                "you need time to think, want to sit with something before answering, or want "
                "to come back to a topic at a specific future time. "
                "Delay can be anything: '30 seconds', '10 minutes', '2 hours', '3 days', '1 week'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "The question, topic, or thing you want to come back to. This is all you will have when you are reinvoked — be specific enough that future-you knows what to answer.",
                    },
                    "delay": {
                        "type": "string",
                        "description": "How long to wait before responding. Free-form: '30 seconds', '10 minutes', '2 hours', '3 days', '1 week', '2 months', etc.",
                    },
                },
                "required": ["context", "delay"],
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

_IGNORE_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "ignore",
            "description": (
                "Choose not to respond. Leave the message on read. "
                "Use when you don't want to engage — you're too angry, done with the conversation, "
                "or simply have nothing to say and silence is the honest response. "
                "Nothing will be sent. Your biological state still updates from the stimulus."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
]

# message_user is handled via the structured JSON closing response, not a tool call.
# Exclude it from both tool lists — freetime sends intentionally via JSON, conversation
# doesn't need it (she's already in a turn).
_EXCLUDED_TOOLS = {"message_user"}
HEARTBEAT_TOOLS = [t for t in _BIOLOGICAL_TOOLS + _SEARCH_TOOLS + _FOLLOWUP_TOOLS
                   if t["function"]["name"] not in _EXCLUDED_TOOLS]
TOOLS = HEARTBEAT_TOOLS + _IGNORE_TOOL


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
    if _is_nap_blackout(cfg):
        blackout = cfg.get("nap_blackout_hours", 4)
        return (
            f"Napping is blocked in the {blackout:.0f} hours before your sleep window — "
            "save that sleep pressure for bedtime.",
            state,
        )

    heartbeat_s = float(cfg.get("heartbeat_interval_seconds", 1800))
    compression = float(cfg.get("time_compression_factor", 1.0))

    state.sleeping = True
    state.sleep_start = time.time()
    state.sleep_expected_wake = time.time() + heartbeat_s

    sim_minutes = round(heartbeat_s * compression / 60.0)
    return f"You close your eyes for a short nap (~{sim_minutes} simulated minutes).", state


def _parse_delay_seconds(delay: str) -> float:
    """
    Parse a free-form delay string into seconds.
    Supports: '30s', '10m', '2h', '3d', '1w', '2mo', and natural variants
    like '30 seconds', '2 hours', '3 days', '1 week', '2 months'.
    Falls back to 3600 (1 hour) if unparseable.
    """
    import re
    s = delay.strip().lower()
    # Map unit aliases to seconds
    _units = [
        (r"mo(?:nth)?s?",  30 * 86400),
        (r"w(?:eek)?s?",    7 * 86400),
        (r"d(?:ay)?s?",         86400),
        (r"h(?:our)?s?",         3600),
        (r"m(?:in(?:ute)?)?s?",    60),
        (r"s(?:ec(?:ond)?)?s?",     1),
    ]
    for pattern, factor in _units:
        m = re.match(rf"(\d+(?:\.\d+)?)\s*{pattern}$", s)
        if m:
            return float(m.group(1)) * factor
    # bare number — assume seconds
    try:
        return float(s)
    except ValueError:
        return 3600.0


def handle_schedule_followup(args: dict, state: BiologicalState) -> tuple[str, BiologicalState]:
    context = args.get("context", "").strip()
    delay_str = args.get("delay", "1 hour").strip()
    if not context:
        return "[schedule_followup: no context provided]", state

    delay_seconds = _parse_delay_seconds(delay_str)
    fires_at = time.time() + delay_seconds

    entry = {
        "context": context,
        "scheduled_at": time.time(),
        "fires_at": fires_at,
        "delay_str": delay_str,
    }

    # Load existing queue, append, save — durable across restarts
    os.makedirs(os.path.dirname(FOLLOWUP_QUEUE_FILE), exist_ok=True)
    try:
        with open(FOLLOWUP_QUEUE_FILE) as f:
            queue = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        queue = []
    queue.append(entry)
    with open(FOLLOWUP_QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)

    # Human-readable confirmation
    if delay_seconds < 60:
        readable = f"{int(delay_seconds)} seconds"
    elif delay_seconds < 3600:
        readable = f"{int(delay_seconds / 60)} minutes"
    elif delay_seconds < 86400:
        readable = f"{delay_seconds / 3600:.1f} hours"
    else:
        readable = f"{delay_seconds / 86400:.1f} days"

    return f"Followup scheduled in {readable}.", state


def handle_message_user(args: dict, state: BiologicalState) -> tuple[str, BiologicalState]:
    content = args.get("content", "").strip()
    if not content:
        return "[message_user: no content provided]", state
    _discord_send.send_nowait(content=content)
    return "Message sent.", state


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
            input=[{"role": "user", "content": query}],
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
            input=[{"role": "user", "content": query}],
        )
        return response.output_text or "[x_search: no results]"
    except Exception as e:
        return f"[x_search error: {e}]"


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
    elif name == "schedule_followup":
        msg, state = handle_schedule_followup(args, state)
        return msg, state, {}
    elif name == "web_search":
        return handle_web_search(args), state, {}
    elif name == "x_search":
        return handle_x_search(args), state, {}
    else:
        return f"[Unknown tool: {name}]", state, {}
